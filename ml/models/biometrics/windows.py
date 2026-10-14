"""User split, session-based enrol/probe split, standardisation and gesture windows.

Open-set protocol: train / valid / test users are disjoint. For valid/test users, sessions 1-12
build the enrolled profile and sessions 13-24 are probes, so a probe never shares a session with
the profile it is compared against.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import FEATURES

ENROL_SESSIONS = range(1, 13)


@dataclass
class Windows:
    x: np.ndarray        # [W, N, F] float32
    user: np.ndarray     # [W]
    session: np.ndarray  # [W]
    scenario: np.ndarray  # [W] 1 = sitting, 2 = walking (majority in window)


def split_users(users, seed: int = 0, frac=(0.7, 0.15)):
    users = np.array(sorted(users))
    rng = np.random.default_rng(seed)
    rng.shuffle(users)
    a, b = int(len(users) * frac[0]), int(len(users) * (frac[0] + frac[1]))
    return set(users[:a]), set(users[a:b]), set(users[b:])


class Standardiser:
    def fit(self, df: pd.DataFrame):
        self.mean = df[FEATURES].mean().to_numpy("float32")
        self.std = df[FEATURES].std().replace(0, 1).to_numpy("float32")
        return self

    def __call__(self, df: pd.DataFrame) -> np.ndarray:
        z = (df[FEATURES].to_numpy("float32") - self.mean) / self.std
        return np.nan_to_num(np.clip(z, -6, 6), nan=0.0)  # missing sensor stats -> population mean


def make_windows(df: pd.DataFrame, z: np.ndarray, n: int, stride: int) -> Windows:
    """Consecutive gestures within one (user, session); windows never cross sessions."""
    xs, us, ss, sc = [], [], [], []
    keys = df[["user", "session"]].to_numpy()
    scen = df["scenario"].fillna(1).to_numpy()
    bounds = np.flatnonzero((keys[1:] != keys[:-1]).any(1)) + 1
    for lo, hi in zip(np.r_[0, bounds], np.r_[bounds, len(df)]):
        for s in range(lo, hi - n + 1, stride):
            xs.append(z[s:s + n])
            us.append(keys[s, 0])
            ss.append(keys[s, 1])
            sc.append(np.round(scen[s:s + n].mean()))
    if not xs:
        return Windows(np.zeros((0, n, z.shape[1]), "float32"), *(np.zeros(0, int) for _ in range(3)))
    return Windows(np.stack(xs).astype("float32"), np.array(us), np.array(ss), np.array(sc).astype(int))


def prepare(df: pd.DataFrame, seed: int = 0):
    """Returns user split dict, fitted standardiser (train users only) and the standardised matrix."""
    tr, va, te = split_users(df["user"].unique(), seed)
    std = Standardiser().fit(df[df["user"].isin(tr)])
    return {"train": tr, "valid": va, "test": te}, std, std(df)
