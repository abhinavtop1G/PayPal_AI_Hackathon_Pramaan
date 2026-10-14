"""Authentication risk model: monotone XGBoost over behaviour, device and transaction features.

* Monotone constraints: risk can only rise with each feature, so explanations always point the right way and an
  attacker cannot lower the score by adding a "risky" signal.
* Missing values (no touch data on web, no geo, login without amount) are learned by XGBoost's default branches.
* Prior correction: the simulator's attack share is far higher than real traffic, so the log-odds are shifted to an
  assumed real-world prevalence (`real_prior`) before the policy uses the probability.
* Signals: tree-SHAP contributions (exact, from XGBoost) per feature, summed per family for the response.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from .features import FAMILY, FEATURES, MONOTONE

ART = Path("ml/auth/artifacts")


def _logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


@dataclass
class AuthModel:
    features: list = field(default_factory=lambda: list(FEATURES))
    real_prior: float = 0.002
    n_estimators: int = 400
    max_depth: int = 4

    def fit(self, X: pd.DataFrame, y, X_valid: pd.DataFrame | None = None, y_valid=None):
        mono = tuple(MONOTONE[FEATURES.index(f)] for f in self.features)
        self.model = xgb.XGBClassifier(n_estimators=self.n_estimators, learning_rate=0.05, max_depth=self.max_depth,
                                       subsample=0.8, colsample_bytree=0.9, min_child_weight=2,
                                       monotone_constraints=mono, tree_method="hist", device="cpu",
                                       eval_metric="aucpr", early_stopping_rounds=50 if X_valid is not None else None)
        kw = {"eval_set": [(X_valid[self.features], y_valid)], "verbose": False} if X_valid is not None else {}
        self.model.fit(X[self.features], y, **kw)
        self.booster = self.model.get_booster()
        self.best_iteration = int(getattr(self.model, "best_iteration", None) or self.n_estimators - 1)
        self.fit_prior = float(np.mean(y))
        self.median = X[self.features].median()
        return self

    @property
    def shift(self) -> float:
        return float(_logit(self.real_prior) - _logit(self.fit_prior))

    def _dm(self, X: pd.DataFrame) -> xgb.DMatrix:
        return xgb.DMatrix(X[self.features].astype("float32"), missing=np.nan)

    def margin(self, X: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(self._dm(X), output_margin=True, iteration_range=(0, self.best_iteration + 1))

    def predict(self, X: pd.DataFrame, prior_corrected: bool = True) -> np.ndarray:
        m = self.margin(X) + (self.shift if prior_corrected else 0.0)
        return 1 / (1 + np.exp(-m))

    def contributions(self, X: pd.DataFrame) -> np.ndarray:
        """[n, n_features + 1] tree-SHAP contributions on the margin (last column = bias)."""
        return self.booster.predict(self._dm(X), pred_contribs=True, iteration_range=(0, self.best_iteration + 1))

    def explain(self, x: dict, top: int = 3) -> tuple[float, list[dict], dict]:
        """Score one request: (prior-corrected probability, signals sorted by contribution, per-family contribution)."""
        X = pd.DataFrame([{f: x.get(f, np.nan) for f in self.features}])
        c = self.contributions(X)[0]
        p = float(1 / (1 + np.exp(-(c.sum() + self.shift))))
        signals = [{"name": f, "family": FAMILY[f], "value": None if not np.isfinite(x.get(f, np.nan)) else round(float(x[f]), 4),
                    "contribution": round(float(v), 4)} for f, v in zip(self.features, c[:-1])]
        signals.sort(key=lambda s: -s["contribution"])
        fam = {k: 0.0 for k in ("behaviour", "device", "transaction")}
        for s in signals:
            fam[s["family"]] += s["contribution"]
        return p, signals, {k: round(v, 4) for k, v in fam.items()}

    # ---------------------------------------------------------------- persistence
    def save(self, directory: Path = ART, name: str = "auth_xgb", extra: dict | None = None):
        directory.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(directory / f"{name}.json")
        (directory / f"{name}.meta.json").write_text(json.dumps({
            "features": self.features, "monotone": [MONOTONE[FEATURES.index(f)] for f in self.features],
            "fit_prior": self.fit_prior, "real_prior": self.real_prior, "best_iteration": self.best_iteration,
            "median": {k: (None if pd.isna(v) else float(v)) for k, v in self.median.items()},
            "xgboost_version": xgb.__version__, **(extra or {})}, indent=2))

    @classmethod
    def load(cls, directory: Path = ART, name: str = "auth_xgb") -> "AuthModel":
        meta = json.loads((Path(directory) / f"{name}.meta.json").read_text())
        m = cls(features=meta["features"], real_prior=meta["real_prior"])
        m.booster = xgb.Booster()
        m.booster.load_model(Path(directory) / f"{name}.json")
        m.booster.set_param({"nthread": 2})
        m.fit_prior, m.best_iteration = meta["fit_prior"], meta["best_iteration"]
        m.median = pd.Series(meta["median"], dtype=float)
        m.meta = meta
        return m
