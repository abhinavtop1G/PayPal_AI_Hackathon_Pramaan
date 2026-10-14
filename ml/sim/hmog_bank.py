"""Real touch gestures for simulated customers, drawn from held-out HMOG users.

Each simulated customer is mapped to one HMOG *test* subject (never seen by the biometrics model in training,
calibration or model selection). Their profile is enrolled from that subject's sessions 1-12; every touch window in a
session is a run of 10 consecutive real gestures from the subject's sessions 13-24 (the same enrol/probe protocol the
model was evaluated with, so a window never shares a session with the profile it is scored against).

What each behavioural profile becomes:
    normal                  the customer's own gestures, unchanged
    distracted / rushed     the customer's own gestures with a mild documented shift (assumption, see PERTURB)
    coerced                 the customer's own gestures with a stronger documented shift (assumption, see PERTURB):
                            HMOG has no coercion labels, so this is the one place the signal is modelled, not measured
    remote                  gestures of a *different* HMOG subject: someone else's hands on the screen
                            (remote-control malware / attacker device), which is exactly what the model was trained for

A window is stored on the event as a compact reference string; `resolve` rebuilds the exact gestures from it, so the
event table stays small and the gestures are reproducible.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ml.models.biometrics.data import CACHE, FEATURES
from ml.models.biometrics.windows import ENROL_SESSIONS, split_users

WINDOW = 10
ENROL_MAX = 240  # gestures per enrolment (spread over sessions 1-12)

# Additive shifts on standardisation-scale features, scaled by the profile intensity. Assumptions, not measurements:
# coercion = slower, more hesitant input (longer gaps and touches) with shakier hands (more motion variance).
PERTURB = {
    "normal": {},
    "distracted": {"log_gap_ms": 0.25, "acc_std": 0.15, "gyr_std": 0.15},
    "rushed": {"log_gap_ms": -0.35, "log_duration_ms": -0.15, "log_speed": 0.20},
    "coerced": {"log_gap_ms": 0.70, "log_duration_ms": 0.20, "acc_std": 0.45, "gyr_std": 0.45},
}


def seeded_rng(*parts) -> np.random.Generator:
    """A private RNG per (session, event): gesture sampling never consumes the simulator's main random stream."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


class HmogBank:
    def __init__(self, gestures: pd.DataFrame):
        _, _, test = split_users(gestures["user"].unique(), 0)  # the biometrics model's held-out test users
        g = gestures[gestures["user"].isin(test)].sort_values(["user", "session", "t_down"], kind="stable")
        self.subjects: list[int] = sorted(int(u) for u in g["user"].unique())
        self.x = g[FEATURES].to_numpy("float64")
        self.scale = np.nanstd(self.x, axis=0)
        self.scale[~np.isfinite(self.scale) | (self.scale == 0)] = 1.0
        keys = g[["user", "session"]].to_numpy()
        self.blocks: dict[tuple[int, int], tuple[int, int]] = {}
        bounds = np.flatnonzero((keys[1:] != keys[:-1]).any(1)) + 1
        for lo, hi in zip(np.r_[0, bounds], np.r_[bounds, len(g)]):
            self.blocks[(int(keys[lo, 0]), int(keys[lo, 1]))] = (int(lo), int(hi))
        self.probe_blocks = {s: [(k, v) for k, v in self.blocks.items() if k[0] == s and k[1] not in ENROL_SESSIONS
                                 and v[1] - v[0] >= WINDOW] for s in self.subjects}
        self.enrol_blocks = {s: [v for k, v in self.blocks.items() if k[0] == s and k[1] in ENROL_SESSIONS]
                             for s in self.subjects}

    # ------------------------------------------------------------------ construction
    @classmethod
    def load(cls, path: Path = CACHE) -> "HmogBank | None":
        """None when the HMOG gesture cache isn't available (the simulator then emits summary numbers only)."""
        return _load(str(path))

    def subject_for(self, user_index: int) -> int:
        return self.subjects[user_index % len(self.subjects)]

    # ------------------------------------------------------------------ gestures
    @staticmethod
    def _dicts(x: np.ndarray) -> list[dict]:
        return [{f: (None if not np.isfinite(v) else round(float(v), 5)) for f, v in zip(FEATURES, row)} for row in x]

    def enrolment(self, subject: int) -> list[dict]:
        rows = np.concatenate([self.x[lo:hi] for lo, hi in self.enrol_blocks[subject]])
        idx = np.linspace(0, len(rows) - 1, min(ENROL_MAX, len(rows))).astype(int)
        return self._dicts(rows[idx])

    def window_ref(self, owner: int, profile: str, intensity: float, rng: np.random.Generator) -> str:
        """Pick a probe window and return its reference: owner|source|session|offset|profile|intensity."""
        source = owner
        if profile == "remote":
            others = [s for s in self.subjects if s != owner]
            source = int(others[int(rng.integers(len(others)))])
        (_, session), (lo, hi) = self.probe_blocks[source][int(rng.integers(len(self.probe_blocks[source])))]
        offset = int(rng.integers(0, hi - lo - WINDOW + 1))
        return f"{owner}|{source}|{session}|{offset}|{profile}|{intensity:.3f}"

    def resolve(self, ref: str) -> tuple[int, list[dict]]:
        """(owner subject, the 10 gestures) for a reference made by `window_ref`."""
        owner, source, session, offset, profile, intensity = ref.split("|")
        lo, _ = self.blocks[(int(source), int(session))]
        x = self.x[lo + int(offset): lo + int(offset) + WINDOW].copy()
        for f, shift in PERTURB.get(profile, {}).items():
            j = FEATURES.index(f)
            x[:, j] += float(intensity) * shift * self.scale[j]
        return int(owner), self._dicts(x)


@lru_cache(maxsize=2)
def _load(path: str) -> HmogBank | None:
    p = Path(path)
    if not p.exists():
        return None
    return HmogBank(pd.read_parquet(p))
