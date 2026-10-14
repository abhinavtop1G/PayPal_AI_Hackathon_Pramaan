"""Train the IEEE-CIS XGBoost baseline with a cost-sensitive ablation.

    python -m ml.models.tabular.train                      # all variants
    python -m ml.models.tabular.train --variants cost --cfp 10

Variants
  plain  - no reweighting
  spw    - scale_pos_weight = #neg / #pos (class-level rebalancing)
  cost   - example-dependent cost: missed fraud costs its TransactionAmt, a false alert costs `cfp`
           (customer friction + ops review). Weights = misclassification cost.

For each variant: early stopping on valid PR-AUC, isotonic calibration on valid, decision threshold
chosen on valid to minimise expected cost, then everything reported once on the time-later test slice.
"""
import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve

from .data import load_ieee, time_split
from .features import build_features

CKPT_DIR = Path("checkpoints/tabular")
REPORT_DIR = Path("ml/reports")

PARAMS = dict(
    n_estimators=4000, learning_rate=0.06, max_depth=8, min_child_weight=4,
    subsample=0.8, colsample_bytree=0.4, reg_lambda=2.0, max_bin=256,
    tree_method="hist", device="cuda", enable_categorical=True, max_cat_to_onehot=1,
    eval_metric="aucpr", early_stopping_rounds=200, random_state=0,
)


# ----------------------------------------------------------------------------- metrics
def recall_at_fpr(y, p, fpr_target=0.01) -> float:
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.interp(fpr_target, fpr, tpr))


def expected_cost(y, p, thr, amt, cfp) -> float:
    alert = p >= thr
    return float(amt[(y == 1) & ~alert].sum() + cfp * ((y == 0) & alert).sum())


def best_threshold(y, p, amt, cfp) -> float:
    grid = np.unique(np.quantile(p, np.linspace(0.5, 0.9999, 600)))
    costs = [expected_cost(y, p, t, amt, cfp) for t in grid]
    return float(grid[int(np.argmin(costs))])


def evaluate(y, p, amt, thr, cfp) -> dict:
    alert = p >= thr
    tp = int(((y == 1) & alert).sum())
    n_alert = int(alert.sum())
    no_model_cost = float(amt[y == 1].sum())  # every fraud slips through
    cost = expected_cost(y, p, thr, amt, cfp)
    return {
        "roc_auc": round(roc_auc_score(y, p), 4),
        "pr_auc": round(average_precision_score(y, p), 4),
        "recall_at_1pct_fpr": round(recall_at_fpr(y, p, 0.01), 4),
        "brier": round(brier_score_loss(y, p), 5),
        "threshold": round(thr, 5),
        "precision_at_thr": round(tp / max(n_alert, 1), 4),
        "recall_at_thr": round(tp / max(int(y.sum()), 1), 4),
        "alerts_per_1k_txn": round(1000 * n_alert / len(y), 2),
        "fraud_amt_caught_pct": round(float(100 * amt[(y == 1) & alert].sum() / max(no_model_cost, 1e-9)), 2),
        "expected_cost": float(round(cost, 0)),
        "cost_saved_vs_no_model_pct": round(100 * (1 - cost / no_model_cost), 2),
    }


# ----------------------------------------------------------------------------- training
def sample_weights(variant: str, y, amt, cfp):
    if variant == "cost":
        w = np.where(y == 1, amt, cfp).astype("float64")
        return w / w.mean()
    return None


def train_variant(variant, X, y, amt, splits, cfp):
    tr, va, te = splits
    params = dict(PARAMS)
    if variant == "spw":
        params["scale_pos_weight"] = float((y[tr] == 0).sum() / (y[tr] == 1).sum())
    model = xgb.XGBClassifier(**params)
    t0 = time.time()
    model.fit(X.iloc[tr], y[tr], sample_weight=sample_weights(variant, y[tr], amt[tr], cfp),
              eval_set=[(X.iloc[va], y[va])], verbose=500)
    train_s = time.time() - t0

    p_va_raw = model.predict_proba(X.iloc[va])[:, 1]
    p_te_raw = model.predict_proba(X.iloc[te])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p_va_raw, y[va])
    p_va, p_te = iso.predict(p_va_raw), iso.predict(p_te_raw)

    thr = best_threshold(y[va], p_va, amt[va], cfp)
    result = {
        "variant": variant,
        "best_iteration": int(model.best_iteration),
        "train_seconds": round(train_s, 1),
        "valid": evaluate(y[va], p_va, amt[va], thr, cfp),
        "test": evaluate(y[te], p_te, amt[te], thr, cfp),
        "test_brier_uncalibrated": round(brier_score_loss(y[te], p_te_raw), 5),
    }
    return model, iso, result


def shap_top_features(model, X_sample, k=25) -> list[dict]:
    dm = xgb.DMatrix(X_sample, enable_categorical=True)
    contrib = model.get_booster().predict(dm, pred_contribs=True)[:, :-1]  # drop bias column
    mean_abs = np.abs(contrib).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][:k]
    return [{"feature": X_sample.columns[i], "mean_abs_shap": round(float(mean_abs[i]), 4)} for i in order]


def write_markdown(report: dict, path: Path):
    cols = ["roc_auc", "pr_auc", "recall_at_1pct_fpr", "precision_at_thr", "recall_at_thr",
            "alerts_per_1k_txn", "fraud_amt_caught_pct", "cost_saved_vs_no_model_pct", "brier"]
    lines = [
        "# IEEE-CIS XGBoost baseline",
        "",
        f"Time-based split: train {report['split']['train']:,} / valid {report['split']['valid']:,} / "
        f"test {report['split']['test']:,} rows; test fraud rate {report['split']['test_fraud_rate']:.2%}. "
        f"False-alert cost c_fp = {report['cfp']}. Threshold chosen on valid, metrics on test.",
        "",
        "| variant | " + " | ".join(cols) + " |",
        "|---|" + "---|" * len(cols),
    ]
    for r in report["variants"]:
        lines.append(f"| {r['variant']} | " + " | ".join(str(r["test"][c]) for c in cols) + " |")
    lines += ["", f"## Top features by mean |SHAP| ({report['shap_variant']} variant)", ""]
    lines += [f"{i + 1}. `{f['feature']}` — {f['mean_abs_shap']}" for i, f in enumerate(report["shap_top"])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variants", nargs="+", default=["plain", "spw", "cost"], choices=["plain", "spw", "cost"])
    ap.add_argument("--cfp", type=float, default=10.0, help="cost of one false alert, in TransactionAmt units (USD)")
    ap.add_argument("--n-estimators", type=int, default=PARAMS["n_estimators"], help="small value = quick dry run")
    ap.add_argument("--refresh-cache", action="store_true")
    args = ap.parse_args()
    PARAMS["n_estimators"] = args.n_estimators

    t0 = time.time()
    df = load_ieee(refresh=args.refresh_cache)
    X, y, amt, _ = build_features(df)
    del df
    splits = time_split(X)
    print(f"loaded + featurised {X.shape} in {time.time() - t0:.0f}s; fraud rate {y.mean():.3%}")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results, models = [], {}
    for v in args.variants:
        print(f"\n=== {v} ===")
        model, iso, res = train_variant(v, X, y, amt, splits, args.cfp)
        model.save_model(CKPT_DIR / f"xgb_{v}.ubj")
        with open(CKPT_DIR / f"iso_{v}.pkl", "wb") as f:
            pickle.dump(iso, f)
        print(json.dumps(res["test"], indent=1, default=float))
        results.append(res)
        models[v] = model

    # pick the variant with the lowest *valid* expected cost (no test peeking) for SHAP
    best = min(results, key=lambda r: r["valid"]["expected_cost"])["variant"]
    te = splits[2]
    sample = X.iloc[np.random.default_rng(0).choice(te, min(20000, len(te)), replace=False)]
    report = {
        "cfp": args.cfp,
        "split": {"train": len(splits[0]), "valid": len(splits[1]), "test": len(te),
                  "test_fraud_rate": float(y[te].mean())},
        "n_features": X.shape[1],
        "variants": results,
        "shap_variant": best,
        "shap_top": shap_top_features(models[best], sample),
    }
    (CKPT_DIR / "feature_names.json").write_text(json.dumps(list(X.columns)))
    (REPORT_DIR / "tabular_baseline.json").write_text(json.dumps(report, indent=2, default=float))
    write_markdown(report, REPORT_DIR / "tabular_baseline.md")
    print(f"\nbest (valid cost): {best}; report -> reports/tabular_baseline.md; total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
