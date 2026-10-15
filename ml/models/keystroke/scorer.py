"""Serving scorer for typing rhythm: enrol a user's password/PIN attempts, then score a new attempt.

Score = mean of z-normalised (CNN cosine to the enrolled mean embedding) and (scaled-Manhattan similarity to the
enrolled timing profile); the normalisation constants and the decision threshold come from valid users
(ml/models/keystroke/evaluate.py), so no dataset is needed at serving time.
`typing_deviation` = threshold - score: > 0 means the attempt looks like someone else's typing.
An attempt is the 31 timings (seconds) in ml.models.keystroke.data.COLUMNS order.
"""
import json
import threading
from pathlib import Path

import numpy as np
import torch

from .data import COLUMNS
from .model import KeystrokeEncoder
from .protocol import profile_cnn, profile_manhattan, score_manhattan

ART = Path("ml/models/keystroke/artifacts")
MIN_ENROL = 5


class KeystrokeScorer:
    def __init__(self, device: str = "cpu", art: Path = ART):
        ck = torch.load(art / "keystroke_cnn.pt", map_location=device, weights_only=False)
        a = ck["args"]
        self.model = KeystrokeEncoder(a["ch"], a["emb"], a["dropout"]).to(device).eval()
        self.model.load_state_dict(ck["state_dict"])
        self.meta = json.loads((art / "keystroke_cnn.meta.json").read_text())
        c = self.meta["calibration"]
        self.norm, self.threshold = c["norm"], c["threshold"]
        self.device = device
        self.profiles: dict[str, dict] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _arr(attempts) -> np.ndarray:
        x = np.asarray(attempts, dtype="float32")
        if x.ndim == 1:
            x = x[None]
        if x.shape[1] != len(COLUMNS) or not np.isfinite(x).all():
            raise ValueError(f"each attempt must be {len(COLUMNS)} finite timings (seconds), order: data.COLUMNS")
        return x

    @torch.no_grad()
    def _embed(self, x: np.ndarray) -> np.ndarray:
        return self.model(torch.as_tensor(x, device=self.device)).cpu().numpy()

    def enroll(self, user_id: str, attempts) -> dict:
        x = self._arr(attempts)
        if len(x) < MIN_ENROL:
            raise ValueError(f"enrolment needs at least {MIN_ENROL} attempts")
        prof = {"cnn": profile_cnn(self._embed(x)), "manhattan": profile_manhattan(x), "n": len(x)}
        with self.lock:
            self.profiles[user_id] = prof
        return {"user_id": user_id, "enrolled": True, "attempts": len(x)}

    def _fused(self, profs: list[dict], x: np.ndarray) -> np.ndarray:
        e = self._embed(x)
        cos = np.array([float(e[i] @ p["cnn"]) for i, p in enumerate(profs)])
        man = np.array([float(score_manhattan(x[i:i + 1], p["manhattan"])[0]) for i, p in enumerate(profs)])
        (m1, s1), (m2, s2) = self.norm["cnn"], self.norm["manhattan"]
        return ((cos - m1) / s1 + (man - m2) / s2) / 2

    def verify(self, user_id: str, attempt) -> dict:
        if user_id not in self.profiles:
            raise KeyError(user_id)
        x = self._arr(attempt)[:1]
        f = float(self._fused([self.profiles[user_id]], x)[0])
        return {"user_id": user_id, "score": round(f, 4), "threshold": round(self.threshold, 4),
                "matches_profile": f >= self.threshold, "typing_deviation": round(self.threshold - f, 4)}

    def deviation_many(self, user_ids: list[str], attempts: np.ndarray, batch: int = 8192) -> np.ndarray:
        """Batched verify(...)['typing_deviation'] for many (enrolled user, attempt) pairs."""
        x = self._arr(attempts)
        out = [self.threshold - self._fused([self.profiles[u] for u in user_ids[i:i + batch]], x[i:i + batch])
               for i in range(0, len(x), batch)]
        return np.concatenate(out) if out else np.zeros(0)
