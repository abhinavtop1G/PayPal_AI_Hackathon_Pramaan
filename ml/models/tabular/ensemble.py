"""CatBoost + LightGBM + XGBoost ensemble on IEEE-CIS, after the 1st-place Kaggle recipe
(Deotte & Yakovlev), adapted to a real-time setting.

    python -m ml.models.tabular.ensemble --fit xgb lgb cat      # train (caches predictions), then blend
    python -m ml.models.tabular.ensemble                        # re-blend from cached predictions only
    python -m ml.models.tabular.ensemble --fit xgb lgb cat --n-estimators 50   # quick dry run

Blends: equal-weight mean, rank mean, and a logistic-regression stack fitted on the valid slice
(the Kaggle stack used LGBM on OOF predictions; with one 59k-row valid slice a linear stacker is safer).

Client post-processing (PP), applied within each scored slice, grouped by uid:
  none    - raw model scores
  causal  - mean of the client's predictions *so far* (current + earlier). Deployable in real time.
  full    - mean over *all* the client's transactions in the slice, including later ones. This is the
            Kaggle PP; it uses the future, so it is reported only as a leaky upper bound.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.linear_model import LogisticRegression

from .data import CATEGORICAL, load_ieee, time_split
from .features import build_features
from .train import PARAMS as XGB_PARAMS, best_threshold, evaluate

CKPT_DIR = Path("checkpoints/tabular/ensemble")
REPORT_DIR = Path("ml/reports")
CFP = 10.0


# ----------------------------------------------------------------------------- base models
def fit_xgb(X, y, tr, va, te, n_estimators):
    import xgboost as xgb
    params = dict(XGB_PARAMS, n_estimators=n_estimators)
    m = xgb.XGBClassifier(**params)
    m.fit(X.iloc[tr], y[tr], eval_set=[(X.iloc[va], y[va])], verbose=500)
    m.save_model(CKPT_DIR / "xgb.ubj")
    return m.predict_proba(X.iloc[va])[:, 1], m.predict_proba(X.iloc[te])[:, 1], int(m.best_iteration)


def fit_lgb(X, y, tr, va, te, n_estimators):
    import lightgbm as lgb
    m = lgb.LGBMClassifier(
        n_estimators=n_estimators, learning_rate=0.05, num_leaves=256, min_child_samples=50,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.4, reg_lambda=2.0, max_bin=255,
        cat_smooth=10, cat_l2=10, n_jobs=-1, verbose=-1, random_state=1,
    )
    m.fit(X.iloc[tr], y[tr], eval_X=(X.iloc[va],), eval_y=(y[va],), eval_metric="average_precision",
          callbacks=[lgb.early_stopping(200, verbose=False), lgb.log_evaluation(500)])
    m.booster_.save_model(str(CKPT_DIR / "lgb.txt"))
    return m.predict_proba(X.iloc[va])[:, 1], m.predict_proba(X.iloc[te])[:, 1], int(m.best_iteration_)


def fit_cat(X, y, tr, va, te, n_estimators):
    from catboost import CatBoostClassifier, Pool
    cats = [c for c in CATEGORICAL if c in X.columns]
    Xc = X.copy()
    for c in cats:  # CatBoost wants strings, no NaN
        Xc[c] = Xc[c].astype("string").fillna("NA").astype(str)
    pool = lambda idx, lab=True: Pool(Xc.iloc[idx], y[idx] if lab else None, cat_features=cats)  # noqa: E731
    m = CatBoostClassifier(
        iterations=n_estimators, learning_rate=0.06, depth=8, l2_leaf_reg=3, border_count=254,
        task_type="GPU", devices="0", eval_metric="AUC", early_stopping_rounds=200,
        random_seed=2, verbose=500,
    )
    m.fit(pool(tr), eval_set=pool(va))
    m.save_model(str(CKPT_DIR / "cat.cbm"))
    return m.predict_proba(pool(va, False))[:, 1], m.predict_proba(pool(te, False))[:, 1], int(m.get_best_iteration())


FITTERS = {"xgb": fit_xgb, "lgb": fit_lgb, "cat": fit_cat}


# ----------------------------------------------------------------------------- post-processing
def pp_causal(p: np.ndarray, uid: np.ndarray) -> np.ndarray:
    """Expanding mean of the client's scores up to and including the current transaction (rows are time-ordered)."""
    s = pd.Series(p)
    g = s.groupby(uid, sort=False)
    return (g.cumsum() / (g.cumcount() + 1)).to_numpy()


def pp_full(p: np.ndarray, uid: np.ndarray) -> np.ndarray:
    """Kaggle PP: every transaction gets the client's mean score over the whole slice (uses the future)."""
    return pd.Series(p).groupby(uid, sort=False).transform("mean").to_numpy()


PP = {"none": lambda p, u: p, "causal": pp_causal, "full": pp_full}


# ----------------------------------------------------------------------------- blending
def _rank01(p):
    return (rankdata(p) - 1) / (len(p) - 1)


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def blends(preds: dict, y_va) -> dict:
    names = sorted(preds)
    out = {n: (preds[n]["va"], preds[n]["te"]) for n in names}
    if len(names) < 2:
        return out
    tag = "+".join(names)
    out[f"mean({tag})"] = (np.mean([preds[n]["va"] for n in names], 0), np.mean([preds[n]["te"] for n in names], 0))
    out[f"rank_mean({tag})"] = (np.mean([_rank01(preds[n]["va"]) for n in names], 0),
                                np.mean([_rank01(preds[n]["te"]) for n in names], 0))
    Zva = np.column_stack([_logit(preds[n]["va"]) for n in names])
    Zte = np.column_stack([_logit(preds[n]["te"]) for n in names])
    lr = LogisticRegression(C=1.0, max_iter=1000).fit(Zva, y_va)
    out[f"stack_lr({tag})"] = (lr.predict_proba(Zva)[:, 1], lr.predict_proba(Zte)[:, 1])
    return out


def score_all(cands: dict, y, amt, uid, va, te) -> list[dict]:
    rows = []
    for name, (p_va, p_te) in cands.items():
        for mode, fn in PP.items():
            q_va, q_te = fn(p_va, uid[va]), fn(p_te, uid[te])
            thr = best_threshold(y[va], q_va, amt[va], CFP)  # rank blends: threshold lives on the rank scale
            m = evaluate(y[te], q_te, amt[te], thr, CFP)
            rows.append({"model": name, "pp": mode, **{k: m[k] for k in (
                "roc_auc", "pr_auc", "recall_at_1pct_fpr", "alerts_per_1k_txn", "cost_saved_vs_no_model_pct")}})
    return rows


def write_markdown(rows, meta, path: Path):
    df = pd.DataFrame(rows)
    lines = [
        "# IEEE-CIS ensemble (CatBoost + LightGBM + XGBoost)",
        "",
        f"Time-based split, metrics on the time-later test slice ({meta['n_test']:,} rows). "
        f"c_fp = {CFP}; thresholds chosen on valid. Base models: "
        + ", ".join(f"{k} (best iter {v['best_iter']}, {v['seconds']:.0f}s)" for k, v in meta["models"].items()) + ".",
        "",
        "PP: `none` raw scores | `causal` client's running mean (deployable) | "
        "`full` client's mean incl. future transactions (Kaggle-style, **leaky upper bound**).",
        "",
        "| model | pp | ROC-AUC | PR-AUC | recall@1%FPR | alerts/1k | cost saved % |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in df.sort_values(["pp", "roc_auc"], ascending=[True, False]).itertuples():
        lines.append(f"| {r.model} | {r.pp} | {r.roc_auc} | {r.pr_auc} | {r.recall_at_1pct_fpr} | "
                     f"{r.alerts_per_1k_txn} | {r.cost_saved_vs_no_model_pct} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fit", nargs="*", default=[], choices=list(FITTERS))
    ap.add_argument("--n-estimators", type=int, default=4000)
    args = ap.parse_args()
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    X, y, amt, uid = build_features(load_ieee())
    tr, va, te = time_split(X)
    print(f"features {X.shape} in {time.time() - t0:.0f}s")

    for name in args.fit:
        print(f"\n=== fit {name} ===")
        t1 = time.time()
        p_va, p_te, best_iter = FITTERS[name](X, y, tr, va, te, args.n_estimators)
        np.savez(CKPT_DIR / f"preds_{name}.npz", va=p_va, te=p_te, best_iter=best_iter, seconds=time.time() - t1)
        print(f"{name}: best_iter={best_iter} ({time.time() - t1:.0f}s)")

    preds, meta = {}, {"n_test": len(te), "models": {}}
    for name in FITTERS:
        f = CKPT_DIR / f"preds_{name}.npz"
        if f.exists():
            z = np.load(f)
            if len(z["te"]) != len(te):
                raise ValueError(f"{f} was produced on a different split; refit it")
            preds[name] = {"va": z["va"], "te": z["te"]}
            meta["models"][name] = {"best_iter": int(z["best_iter"]), "seconds": float(z["seconds"])}
    if not preds:
        raise SystemExit("no cached predictions; run with --fit")

    rows = score_all(blends(preds, y[va]), y, amt, uid, va, te)
    (REPORT_DIR / "tabular_ensemble.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=2, default=float))
    write_markdown(rows, meta, REPORT_DIR / "tabular_ensemble.md")
    print("\n" + (REPORT_DIR / "tabular_ensemble.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
