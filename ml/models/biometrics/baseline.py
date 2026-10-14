"""Non-sequential baselines on the same windows and protocol as the LSTM.

    python -m ml.models.biometrics.baseline

  stats_cosine - per-window mean + std of each gesture feature, standardised on train users, cosine to profile
  stats_lda    - same statistics projected with LDA fitted on train users (a learned linear embedding)
"""
import json
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

from .data import load_gestures
from .metrics import verify
from .train import EVAL_LENGTHS
from .windows import make_windows, prepare

REPORT_DIR = Path("ml/reports")


def window_stats(x: np.ndarray) -> np.ndarray:
    return np.concatenate([x.mean(1), x.std(1)], 1)


def main(split_seed: int = 0):
    df = load_gestures()
    split, _, z = prepare(df, split_seed)
    part = {k: df["user"].isin(v).to_numpy() for k, v in split.items()}
    results = {"stats_cosine": {}, "stats_lda": {}}
    for n in EVAL_LENGTHS:
        tr = make_windows(df[part["train"]], z[part["train"]], n, stride=max(1, n // 2))
        s_tr = window_stats(tr.x)
        mu, sd = s_tr.mean(0), s_tr.std(0) + 1e-6
        lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto").fit((s_tr - mu) / sd, tr.user)
        for split_name in ("valid", "test"):
            w = make_windows(df[part[split_name]], z[part[split_name]], n, stride=n)
            s = (window_stats(w.x) - mu) / sd
            results["stats_cosine"].setdefault(split_name, {})[f"n{n}"] = verify(s, w.user, w.session, w.scenario)
            results["stats_lda"].setdefault(split_name, {})[f"n{n}"] = verify(lda.transform(s), w.user, w.session, w.scenario)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "biometrics_hmog_baselines.json").write_text(json.dumps(results, indent=2, default=float))
    for name, r in results.items():
        print(name, "TEST", {k: v["eer"] for k, v in r["test"].items()})


if __name__ == "__main__":
    main()
