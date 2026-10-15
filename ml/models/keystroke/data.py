"""CMU keystroke benchmark (Killourhy & Maxion 2009): 51 subjects type the password `.tie5Roanl` 400 times
(8 sessions x 50 repetitions). Each attempt has 31 timings in seconds: for each of the 11 keys its hold time
H.<key>, and between consecutive keys the down-down latency DD.<a>.<b> and up-down latency UD.<a>.<b> (UD < 0 when
the next key goes down before the previous one comes up).

    KEYSTROKE_CSV=... python -m ml.models.keystroke.train      # default path: DATA/keystroke/DSL-StrongPasswordData.csv
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ["period", "t", "i", "e", "five", "Shift.r", "o", "a", "n", "l", "Return"]
COLUMNS = [c for a, b in zip(KEYS, KEYS[1:]) for c in (f"H.{a}", f"DD.{a}.{b}", f"UD.{a}.{b}")] + [f"H.{KEYS[-1]}"]
PATH = Path(os.environ.get("KEYSTROKE_CSV", "DATA/keystroke/DSL-StrongPasswordData.csv"))
ENROL_SESSIONS = range(1, 5)   # profile from sessions 1-4, probes from sessions 5-8


def load_cmu(path: Path = PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"not the CMU keystroke file: missing {sorted(missing)[:5]}")
    df["user"] = df["subject"].str.slice(1).astype(int)
    return df.rename(columns={"sessionIndex": "session"})


def timings(df: pd.DataFrame) -> np.ndarray:
    """[N, 31] float32 timings in COLUMNS order (H, DD, UD per key pair, then the last key's H)."""
    return df[COLUMNS].to_numpy("float32")
