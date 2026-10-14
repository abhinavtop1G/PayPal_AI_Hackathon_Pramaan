"""Load IEEE-CIS (train_transaction + train_identity) into one memory-lean frame, cached as parquet.

Only the labelled `train_*` files are used; the Kaggle `test_*` files have no labels, so our
held-out evaluation is a time-later slice of train (see train.py).
"""
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path("DATA")
CACHE = Path("data/ieee/train_merged.parquet")

CATEGORICAL = (
    ["ProductCD", "card4", "card6", "P_emaildomain", "R_emaildomain", "DeviceType", "DeviceInfo"]
    + [f"M{i}" for i in range(1, 10)]
    + [f"id_{i}" for i in range(12, 39)]
)


def _read_csv(path: Path) -> pd.DataFrame:
    head = pd.read_csv(path, nrows=0).columns
    dtypes = {c: "float32" for c in head if c not in CATEGORICAL and c not in ("TransactionID", "isFraud", "TransactionDT")}
    for c in head:
        if c in CATEGORICAL:
            dtypes[c] = "string"
    return pd.read_csv(path, dtype=dtypes)


def load_ieee(raw_dir: Path = RAW_DIR, cache: Path = CACHE, refresh: bool = False) -> pd.DataFrame:
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    tx = _read_csv(raw_dir / "train_transaction.csv")
    ident = _read_csv(raw_dir / "train_identity.csv")
    df = tx.merge(ident, on="TransactionID", how="left")
    df["has_identity"] = df["TransactionID"].isin(ident["TransactionID"]).astype("int8")
    df["isFraud"] = df["isFraud"].astype("int8")
    df["TransactionDT"] = df["TransactionDT"].astype("int64")
    df = df.sort_values("TransactionDT", kind="stable").reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def time_split(df: pd.DataFrame, train_frac: float = 0.7, valid_frac: float = 0.1):
    """Chronological train / valid / test index arrays (df must be sorted by TransactionDT)."""
    n = len(df)
    a, b = int(n * train_frac), int(n * (train_frac + valid_frac))
    idx = np.arange(n)
    return idx[:a], idx[a:b], idx[b:]
