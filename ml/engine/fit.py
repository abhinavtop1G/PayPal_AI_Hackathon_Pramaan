"""Fit the fusion model exactly as engine.simulate does and save it for serving.

    python -m ml.engine.oof      # once (out-of-fold GRU scores for the training period)
    python -m ml.engine.fit      # -> engine/artifacts/fusion_xgb.json + fusion_meta.json
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .components import build_tables
from .fusion import FusionModel
from .oof import OUT as OOF

ART_DIR = Path(os.environ.get("RAKSHAM_FUSION_DIR", "ml/engine/artifacts"))


def fit_fusion() -> FusionModel:
    if not OOF.exists():
        raise SystemExit("missing out-of-fold scores: run `python -m ml.engine.oof` first")
    tv, dv = build_tables()["valid"]
    cut = dv.sessions["start_time"].median()
    tA = tv[tv["session_idx"].isin(np.flatnonzero(dv.sessions["start_time"] < cut))]
    return FusionModel(real_prior=0.005).fit(pd.concat([pd.read_parquet(OOF), tA]))


if __name__ == "__main__":
    f = fit_fusion()
    f.save(ART_DIR)
    print(f"saved fusion to {ART_DIR} (fit prior {f.fit_prior:.3f}, real prior {f.real_prior})")
