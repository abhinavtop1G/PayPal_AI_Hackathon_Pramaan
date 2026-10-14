"""IEEE-CIS XGBoost transaction-risk scoring from engineered features (CPU).

Requests carry the engineered feature vector (models.tabular.features.build_features). Computing the
per-customer history features online needs a feature store, which is out of scope here.
The serving model (models.tabular.export) uses label-encoded categoricals, so requests map straight to a
float32 array (category -> index in the training vocabulary, unknown/missing -> NaN) and CPU and GPU
predictors agree. Serving on CPU keeps XGBoost off GPU worker threads (that combination fail-fasts the
process on Windows when the model is freed) and avoids pandas entirely.
"""
import json
import threading
from pathlib import Path

import numpy as np
import xgboost as xgb

ART = Path("ml/models/tabular/artifacts")


class TabularService:
    def __init__(self, device: str = "cpu"):
        self.meta = json.loads((ART / "xgb_ieee.meta.json").read_text())
        self.features = self.meta["feature_names"]
        self.col = {f: i for i, f in enumerate(self.features)}
        self.vocab = json.loads((ART / "xgb_ieee.categories.json").read_text())
        self._code = {c: {v: i for i, v in enumerate(vs)} for c, vs in self.vocab.items()}
        self.booster = xgb.Booster()
        self.booster.load_model(ART / "xgb_ieee.ubj")
        self.booster.set_param({"device": "cpu", "nthread": 4})
        self.iteration_range = (0, int(self.meta["best_iteration"]) + 1)  # early-stopping best, as evaluated
        self.device = "cpu"
        self.lock = threading.Lock()

    def encode(self, records: list[dict]) -> np.ndarray:
        unknown = set().union(*map(set, records)) - set(self.col)
        if unknown:
            raise ValueError(f"unknown features: {sorted(unknown)[:10]}")
        a = np.full((len(records), len(self.features)), np.nan, dtype="float32")
        for i, r in enumerate(records):
            for k, v in r.items():
                if v is None:
                    continue
                j = self.col[k]
                if k in self._code:
                    a[i, j] = self._code[k].get(str(v), np.nan)
                else:
                    try:
                        a[i, j] = float(v)
                    except (TypeError, ValueError) as e:
                        raise ValueError(f"feature {k} must be numeric, got {v!r}") from e
        return a

    def score(self, records: list[dict]) -> dict:
        a = self.encode(records)
        with self.lock:
            p = self.booster.inplace_predict(a, iteration_range=self.iteration_range)
        missing = np.isnan(a).sum(1).astype(int).tolist()
        return {"p_fraud": [round(float(x), 6) for x in p], "missing_features": missing,
                "model": "XGBoost (IEEE-CIS, causal features, label-encoded categoricals)", "device": self.device}
