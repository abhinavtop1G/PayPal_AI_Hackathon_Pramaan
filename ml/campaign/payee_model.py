"""Payee-risk model: P(this receiving account is a mule | its recent credit/debit behaviour).

XGBoost on the causal features of ml.campaign.features, isotonic-calibrated on a later validation slice,
with reason codes from tree-SHAP contributions (xgboost's own `pred_contribs`, no extra dependency).

Why this replaces the simulator's `payee_mule_score` stand-in: that score was drawn from the ground-truth
label with noise. This one is computed from transfers only, so it is wrong in the places a real model
would be wrong (cold-start accounts with no history, slow mules, busy benign merchants).
"""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

from .features import DIRECTION, FEATURES, MODEL_FEATURES, REASON_TEXT

ART_DIR = Path("ml/campaign/artifacts")
PARAMS = dict(n_estimators=400, learning_rate=0.05, max_depth=5, subsample=0.8, colsample_bytree=0.8,
              min_child_weight=3, tree_method="hist", n_jobs=8, random_state=0, eval_metric="aucpr")


@dataclass
class PayeeRiskModel:
    booster: xgb.Booster  # plain Booster: loads without the sklearn wrapper, so it works across xgboost/sklearn versions
    iso_x: np.ndarray
    iso_y: np.ndarray
    benign_median: dict
    meta: dict

    # ---------------------------------------------------------------- scoring
    def raw(self, X: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(xgb.DMatrix(X[MODEL_FEATURES]))

    def calibrate(self, p: np.ndarray) -> np.ndarray:
        return np.interp(p, self.iso_x, self.iso_y)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.calibrate(self.raw(X))

    def reasons(self, x: np.ndarray | pd.Series, k: int = 3) -> list[tuple[str, float]]:
        """Top-k risk-raising features that also sit on their risky side of the benign median."""
        row = pd.DataFrame([np.asarray(x, dtype="float64")], columns=FEATURES)
        view = row[MODEL_FEATURES]
        contrib = self.booster.predict(xgb.DMatrix(view), pred_contribs=True)[0, :-1]
        out = []
        for f, c in sorted(zip(MODEL_FEATURES, contrib), key=lambda t: -t[1]):
            if c <= 0 or f not in REASON_TEXT:
                continue
            v, med, d = row.at[0, f], self.benign_median.get(f, np.nan), DIRECTION[f]
            if np.isnan(v) or (not np.isnan(med) and d * (v - med) <= 0):
                continue
            out.append((REASON_TEXT[f], round(float(c), 3)))
            if len(out) == k:
                break
        return out

    # ---------------------------------------------------------------- persistence
    def save(self, directory: Path = ART_DIR) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(directory / "payee_risk_xgb.json")
        (directory / "payee_risk_meta.json").write_text(json.dumps({
            "features": MODEL_FEATURES, "iso_x": self.iso_x.tolist(), "iso_y": self.iso_y.tolist(),
            "benign_median": self.benign_median, "meta": self.meta, "xgboost_version": xgb.__version__}, indent=2))

    @classmethod
    def load(cls, directory: Path = ART_DIR) -> "PayeeRiskModel":
        directory = Path(directory)
        m = json.loads((directory / "payee_risk_meta.json").read_text())
        assert m["features"] == MODEL_FEATURES, "feature list changed since this model was trained; retrain"
        b = xgb.Booster()
        b.load_model(directory / "payee_risk_xgb.json")
        return cls(b, np.array(m["iso_x"]), np.array(m["iso_y"]), m["benign_median"], m["meta"])


def _fit_booster(X, y, X_val=None, y_val=None, n_estimators=None):
    params = dict(PARAMS)
    if n_estimators:
        params["n_estimators"] = n_estimators
    pos = max(1.0, float(y.sum()))
    params["scale_pos_weight"] = float(np.sqrt((len(y) - pos) / pos))  # soften the imbalance, keep probabilities usable
    b = xgb.XGBClassifier(**params)
    if X_val is not None and len(X_val) and y_val.nunique() > 1:
        b.set_params(early_stopping_rounds=40)
        b.fit(X[MODEL_FEATURES], y, eval_set=[(X_val[MODEL_FEATURES], y_val)], verbose=False)
    else:
        b.fit(X[MODEL_FEATURES], y)
    return b


def fit(X: pd.DataFrame, y: pd.Series, day: pd.Series, groups: pd.Series, split_days=(60, 75), oof_folds: int = 5):
    """Time split: train < split_days[0] <= valid < split_days[1] <= test.

    Returns (model, scores) where `scores` are calibrated risk scores for *every* row, honest for use as a
    downstream feature: rows in the training period come from account-grouped out-of-fold models, later
    rows from the model trained on the training period only.
    """
    tr = (day < split_days[0]).to_numpy()
    va = ((day >= split_days[0]) & (day < split_days[1])).to_numpy()
    booster = _fit_booster(X[tr], y[tr], X[va], y[va])
    raw = np.full(len(X), np.nan)
    raw[~tr] = booster.predict_proba(X.loc[~tr, MODEL_FEATURES])[:, 1]
    Xt, yt, gt = X[tr], y[tr], groups[tr].to_numpy()
    oof = np.zeros(len(Xt))
    for a, b in GroupKFold(n_splits=oof_folds).split(Xt, yt, gt):
        m = _fit_booster(Xt.iloc[a], yt.iloc[a], n_estimators=booster.best_iteration + 1 if getattr(booster, "best_iteration", None) else None)
        oof[b] = m.predict_proba(Xt.iloc[b][MODEL_FEATURES])[:, 1]
    raw[tr] = oof
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw[va], y[va])
    xs = np.concatenate([[0.0], iso.X_thresholds_, [1.0]])
    ys = np.concatenate([[iso.y_thresholds_[0]], iso.y_thresholds_, [iso.y_thresholds_[-1]]])
    benign = X[(~y.astype(bool)).to_numpy()]
    med = {f: float(np.nanmedian(benign[f])) for f in FEATURES}
    bst = booster.get_booster()
    if getattr(booster, "best_iteration", None) is not None:
        bst = bst[: booster.best_iteration + 1]  # keep only the trees up to the early-stopping point
    model = PayeeRiskModel(bst, xs, ys, med, {"split_days": list(split_days), "n_train": int(tr.sum()),
                                                  "n_valid": int(va.sum()), "train_positive_rate": float(y[tr].mean())})
    return model, model.calibrate(raw)
