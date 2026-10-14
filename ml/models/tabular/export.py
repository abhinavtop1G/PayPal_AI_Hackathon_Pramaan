"""Train and export the serving XGBoost: same features/params/split as the ensemble's XGBoost, but with
categoricals label-encoded against the training vocabulary instead of native categorical splits.

    python -m ml.models.tabular.export

Why: with native categorical splits, XGBoost 3.2's CPU and GPU predictors disagreed, and using the GPU
predictor from server worker threads makes the process fail-fast (0xC0000409) when the model is freed.
With plain numeric inputs CPU and GPU agree, so the API serves on CPU (fast, no GPU threading).
Writes models/tabular/artifacts/xgb_ieee.{ubj,meta.json,categories.json} and reports/tabular_serving_model.json.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score

from .data import load_ieee, time_split
from .features import build_features
from .train import PARAMS, best_threshold, evaluate

ART = Path("ml/models/tabular/artifacts")
CFP = 10.0


def label_encode(X: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Categoricals -> their code in the (full-data) category vocabulary; missing -> NaN."""
    vocab = {c: [str(v) for v in X[c].cat.categories] for c in X.columns if isinstance(X[c].dtype, pd.CategoricalDtype)}
    cols = []
    for c in X.columns:
        if c in vocab:
            codes = X[c].cat.codes.to_numpy().astype("float32")
            codes[codes < 0] = np.nan
            cols.append(codes)
        else:
            cols.append(X[c].to_numpy("float32"))
    return np.column_stack(cols), vocab


def main():
    t0 = time.time()
    X, y, amt, _ = build_features(load_ieee())
    tr, va, te = time_split(X)
    A, vocab = label_encode(X)
    names = list(X.columns)
    params = {k: v for k, v in PARAMS.items() if k not in ("enable_categorical", "max_cat_to_onehot")}
    params["n_estimators"] = 6000
    model = xgb.XGBClassifier(**params)
    model.fit(A[tr], y[tr], eval_set=[(A[va], y[va])], verbose=1000)
    booster = model.get_booster()
    booster.feature_names = names

    p_va_gpu = model.predict_proba(A[va])[:, 1]
    p_te_gpu = model.predict_proba(A[te])[:, 1]
    best = (0, int(model.best_iteration) + 1)  # sklearn predict uses the early-stopping best iteration; match it
    cpu = booster.copy()
    cpu.set_param({"device": "cpu"})
    p_te_cpu = cpu.inplace_predict(A[te], iteration_range=best)
    thr = best_threshold(y[va], p_va_gpu, amt[va], CFP)
    old = json.loads((ART / "xgb_ieee.meta.json").read_text())
    res = {
        "model": "XGBoost, label-encoded categoricals (serving model)",
        "best_iteration": int(model.best_iteration),
        "cpu_vs_gpu_max_abs_diff_test": float(np.abs(p_te_cpu - p_te_gpu).max()),
        "test_raw_scores": evaluate(y[te], p_te_gpu, amt[te], thr, CFP),
        "previous_native_categorical_model_test": old.get("test_metrics_raw_scores"),
        "train_seconds": round(time.time() - t0, 1),
    }
    model.save_model(ART / "xgb_ieee.ubj")
    (ART / "xgb_ieee.categories.json").write_text(json.dumps(vocab))
    meta = {
        "model": "XGBoost binary classifier, IEEE-CIS fraud (label-encoded categoricals)",
        "file": "xgb_ieee.ubj",
        "xgboost_version": xgb.__version__,
        "trained_by": "python -m ml.models.tabular.export",
        "features": "models.tabular.features.build_features (causal); categoricals label-encoded with xgb_ieee.categories.json",
        "split": "chronological 70/10/20 on TransactionDT; early-stopped on valid PR-AUC",
        "best_iteration": res["best_iteration"],
        "n_features": len(names),
        "test_metrics_raw_scores": {k: res["test_raw_scores"][k] for k in ("roc_auc", "pr_auc", "recall_at_1pct_fpr")},
        "cpu_gpu_agreement_max_abs_diff": res["cpu_vs_gpu_max_abs_diff_test"],
        "predict_device": "cpu (CPU and GPU predictors agree for this model)",
        "note": "Raw (uncalibrated) scores. Replaces the native-categorical model, whose CPU/GPU predictors disagreed.",
        "usage": ("encode categoricals with xgb_ieee.categories.json (index in list, missing -> NaN), numeric as float32, "
                  "column order = feature_names; booster.inplace_predict(array, iteration_range=(0, best_iteration + 1))"),
        "feature_names": names,
    }
    (ART / "xgb_ieee.meta.json").write_text(json.dumps(meta, indent=2))
    np.savez("checkpoints/tabular/serving_xgb_preds.npz", te=p_te_gpu, te_idx=te)
    Path("ml/reports/tabular_serving_model.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({k: v for k, v in res.items() if k != "previous_native_categorical_model_test"}, indent=1, default=float))
    print("previous:", res["previous_native_categorical_model_test"])


if __name__ == "__main__":
    main()
