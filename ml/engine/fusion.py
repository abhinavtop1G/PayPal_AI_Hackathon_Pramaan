"""Monotone gradient-boosted fusion of component scores, with prior correction and reason codes.

Why not logistic regression: the GRU already consumes payee features, so a linear stacker was
collinear and learned a *negative* weight on mule score, which also produced misleading reasons.
Monotone constraints keep every input pointing the right way (risk can only rise with GRU score,
mule score, behavioural deviation, amount, new payee and unknown caller; only fall for trusted
payees) while still learning interactions such as "scam-like workflow but clean payee".

Trained on rows the GRU never saw: out-of-fold GRU scores for the training period (engine/oof.py)
plus the first half of the valid period, with hard negatives up-weighted (chosen on valid half B). The intercept is shifted from the
simulator's scam share to a configurable real-world prior before the policy uses the probability.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb

INPUTS = ["gru_p", "mule_score", "bio_dev", "log_amt_vs_avg", "payee_is_new", "unknown_call_active",
          "caller_reported_active", "payee_known_trusted"]
FEATURES = ["gru_logit", "mule_score", "bio_dev", "log_amt_vs_avg", "payee_is_new", "unknown_call_active",
            "caller_reported_active", "payee_known_trusted"]
MONOTONE = (1, 1, 1, 1, 1, 1, 1, -1)
REASON_TEXT = {
    "gru_logit": "session follows a known scam pattern",
    "mule_score": "receiving account is linked to suspected mule activity",
    "bio_dev": "touch behaviour differs from your usual pattern",
    "log_amt_vs_avg": "amount is much larger than your usual payments",
    "payee_is_new": "first payment to this account",
    "unknown_call_active": "you are on a call with an unknown number",
    "caller_reported_active": "the number calling you has been reported for fraud",
}


def design(t: pd.DataFrame) -> pd.DataFrame:
    t = t[INPUTS].astype(float)  # single rows arrive as object dtype
    p = t["gru_p"].clip(1e-6, 1 - 1e-6)
    x = t.drop(columns="gru_p")
    x.insert(0, "gru_logit", np.log(p / (1 - p)).clip(-12, 12))
    return x[FEATURES]


@dataclass
class FusionModel:
    real_prior: float = 0.005  # share of payment attempts that are part of an active scam in real traffic
    n_estimators: int = 300
    hard_weight: float = 10.0  # up-weight legitimate attempts the GRU finds scam-like (hard negatives)
    hard_p: float = 0.2

    def fit(self, t: pd.DataFrame, y_col: str = "in_progress"):
        X = design(t)
        self.median = X.median()
        hard = (~t["is_scam"].astype(bool)) & (t["gru_p"] > self.hard_p)
        self.model = xgb.XGBClassifier(n_estimators=self.n_estimators, learning_rate=0.05, max_depth=3, subsample=0.8,
                                       monotone_constraints=MONOTONE, tree_method="hist", device="cpu")
        self.model.fit(X, t[y_col], sample_weight=np.where(hard, self.hard_weight, 1.0))
        self.booster = self.model.get_booster()
        self.fit_prior = float(t[y_col].mean())
        return self.set_prior(self.real_prior)

    def set_prior(self, real_prior: float):
        """Re-target the probability to a different assumed real-world scam prevalence (no refit)."""
        self.real_prior = real_prior
        self.prior_shift = np.log(real_prior / (1 - real_prior)) - np.log(self.fit_prior / (1 - self.fit_prior))
        return self

    def logit(self, t: pd.DataFrame, real_prior: bool = True) -> np.ndarray:
        z = self.booster.predict(xgb.DMatrix(design(t)), output_margin=True)
        return z + (self.prior_shift if real_prior else 0.0)

    def proba(self, t: pd.DataFrame, real_prior: bool = True) -> np.ndarray:
        return 1 / (1 + np.exp(-self.logit(t, real_prior)))

    def reasons(self, row: pd.DataFrame, k: int = 3) -> list[tuple[str, float]]:
        """Top-k inputs pushing risk up (SHAP contribution > 0) *and* sitting on their risky side
        (above the training median), so a reason never contradicts the data."""
        X = design(row)
        contrib = self.booster.predict(xgb.DMatrix(X), pred_contribs=True)[0, :-1]
        s = pd.Series(contrib, index=FEATURES)
        risky = (X.iloc[0] > self.median) & s.index.isin(list(REASON_TEXT))
        top = s[(s > 0) & risky].sort_values(ascending=False).head(k)
        return [(REASON_TEXT[f], round(float(v), 3)) for f, v in top.items()]

    def save(self, directory) -> None:
        from pathlib import Path
        import json
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(d / "fusion_xgb.json")
        (d / "fusion_meta.json").write_text(json.dumps({
            "real_prior": self.real_prior, "fit_prior": self.fit_prior, "median": self.median.to_dict(),
            "features": FEATURES, "monotone": MONOTONE, "hard_weight": self.hard_weight, "hard_p": self.hard_p,
            "xgboost_version": xgb.__version__}, indent=2))

    @classmethod
    def load(cls, directory) -> "FusionModel":
        from pathlib import Path
        import json
        d = Path(directory)
        meta = json.loads((d / "fusion_meta.json").read_text())
        f = cls(real_prior=meta["real_prior"], hard_weight=meta["hard_weight"], hard_p=meta["hard_p"])
        f.booster = xgb.Booster()  # plain Booster: loads without the scikit-learn wrapper
        f.booster.load_model(d / "fusion_xgb.json")
        f.median = pd.Series(meta["median"])[FEATURES]
        f.fit_prior = meta["fit_prior"]
        return f.set_prior(meta["real_prior"])

    def importance(self) -> dict:
        g = self.booster.get_score(importance_type="gain")
        return {f: round(float(g.get(f, 0.0)), 2) for f in FEATURES}
