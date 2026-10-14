"""Behavioural biometrics scorer: enrol a user's gesture profile, then verify gesture windows against it.

Shared by the API (backend/bio_service.py) and the offline session pipeline (ml/engine/components.py via
ml/models/biometrics/session_scores.py), so a touch window gets the same score in training and in serving.

Score = BiLSTM + LDA score fusion (as recommended in ml/reports/biometrics_hmog.md). At first start the
service calibrates from the HMOG gesture cache and saves checkpoints/serve/bio_calib.pkl:
  * LDA on train users' window statistics (per window length N = 10, 20)
  * z-normalisation constants for each model's similarities, from valid users
  * the fused-score threshold at the valid-user EER
Gestures are the per-gesture features of ml.models.biometrics.data.FEATURES (client-side extraction).
"""
import pickle
import threading
from pathlib import Path

import numpy as np
import torch
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import roc_curve

from ml.models.biometrics.baseline import window_stats
from ml.models.biometrics.data import FEATURES, load_gestures
from ml.models.biometrics.metrics import similarity
from ml.models.biometrics.model import GestureEncoder
from ml.models.biometrics.windows import make_windows, prepare

ART = Path("ml/models/biometrics/artifacts/hmog_bilstm.pt")
CALIB = Path("checkpoints/serve/bio_calib.pkl")
LENGTHS = (10, 20)


def _unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True).clip(min=1e-12)


class BioScorer:
    def __init__(self, device: str = "cuda"):
        self.device = device
        ck = torch.load(ART, weights_only=False, map_location=device)
        a = ck["args"]
        self.enc = GestureEncoder(len(FEATURES), a["hidden"], emb=a["emb"], dropout=a["dropout"]).to(device).eval()
        self.enc.load_state_dict(ck["state_dict"])
        self.mean, self.std = np.asarray(ck["std_mean"]), np.asarray(ck["std_std"])
        self.calib = self._load_or_calibrate()
        self.profiles: dict[str, dict] = {}
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ features
    def _z(self, gestures: list[dict]) -> np.ndarray:
        x = np.array([[np.nan if g.get(f) is None else float(g[f]) for f in FEATURES] for g in gestures], dtype="float32")
        return np.nan_to_num(np.clip((x - self.mean) / self.std, -6, 6), nan=0.0)

    @torch.no_grad()
    def _lstm(self, windows: np.ndarray) -> np.ndarray:
        return self.enc(torch.as_tensor(windows, device=self.device)).cpu().numpy()

    def _lda(self, n: int, windows: np.ndarray, calib: dict | None = None) -> np.ndarray:
        c = (calib if calib is not None else self.calib)[n]
        return c["lda"].transform((window_stats(windows) - c["mu"]) / c["sd"])

    # ------------------------------------------------------------------ calibration
    def _load_or_calibrate(self) -> dict:
        if CALIB.exists():
            return pickle.loads(CALIB.read_bytes())
        df = load_gestures()
        split, _, z = prepare(df, 0)
        part = {k: df["user"].isin(v).to_numpy() for k, v in split.items()}
        calib = {}
        for n in LENGTHS:
            tr = make_windows(df[part["train"]], z[part["train"]], n, stride=max(1, n // 2))
            s_tr = window_stats(tr.x)
            mu, sd = s_tr.mean(0), s_tr.std(0) + 1e-6
            lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto").fit((s_tr - mu) / sd, tr.user)
            calib[n] = {"lda": lda, "mu": mu, "sd": sd}
            w = make_windows(df[part["valid"]], z[part["valid"]], n, stride=n)
            s_lstm, owner, _ = similarity(self._lstm(w.x), w.user, w.session)
            s_lda, _, _ = similarity(self._lda(n, w.x, calib), w.user, w.session)
            norm = {"lstm": (float(s_lstm.mean()), float(s_lstm.std())), "lda": (float(s_lda.mean()), float(s_lda.std()))}
            fused = ((s_lstm - norm["lstm"][0]) / norm["lstm"][1] + (s_lda - norm["lda"][0]) / norm["lda"][1]) / 2
            gen = np.zeros_like(fused, bool)
            gen[np.arange(len(owner)), owner] = True
            fpr, tpr, thr = roc_curve(gen.ravel(), fused.ravel())
            i = np.nanargmin(np.abs((1 - tpr) - fpr))
            calib[n].update(norm=norm, threshold=float(thr[i]), valid_eer=float((fpr[i] + 1 - tpr[i]) / 2))
        CALIB.parent.mkdir(parents=True, exist_ok=True)
        CALIB.write_bytes(pickle.dumps(calib))
        return calib

    # ------------------------------------------------------------------ API
    def enroll(self, user_id: str, gestures: list[dict]) -> dict:
        if len(gestures) < 20:
            raise ValueError("enrolment needs at least 20 gestures")
        z = self._z(gestures)
        prof = {}
        for n in LENGTHS:
            w = np.stack([z[s:s + n] for s in range(0, len(z) - n + 1, max(1, n // 2))])
            prof[n] = {"lstm": _unit(_unit(self._lstm(w)).mean(0)), "lda": _unit(_unit(self._lda(n, w)).mean(0)),
                       "n_windows": len(w)}
        with self.lock:
            self.profiles[user_id] = prof
        return {"user_id": user_id, "enrolled": True, "gestures": len(gestures),
                "windows": {f"n{n}": prof[n]["n_windows"] for n in LENGTHS}}

    def verify(self, user_id: str, gestures: list[dict]) -> dict:
        if user_id not in self.profiles:
            raise KeyError(user_id)
        if len(gestures) < 10:
            raise ValueError("verification needs at least 10 gestures")
        n = 20 if len(gestures) >= 20 else 10
        w = self._z(gestures)[-n:][None]
        p, c = self.profiles[user_id][n], self.calib[n]
        s_lstm = float(_unit(self._lstm(w))[0] @ p["lstm"])
        s_lda = float(_unit(self._lda(n, w))[0] @ p["lda"])
        (m1, sd1), (m2, sd2) = c["norm"]["lstm"], c["norm"]["lda"]
        fused = ((s_lstm - m1) / sd1 + (s_lda - m2) / sd2) / 2
        return {"user_id": user_id, "window_gestures": n, "similarity_lstm": round(s_lstm, 4), "similarity_lda": round(s_lda, 4),
                "fused_score": round(fused, 4), "threshold_at_eer": round(c["threshold"], 4),
                "matches_profile": fused >= c["threshold"], "behavioural_deviation": round(c["threshold"] - fused, 4),
                "valid_eer": round(c["valid_eer"], 4)}

    def deviation_many(self, user_ids: list[str], windows: list[list[dict]], n: int = 10) -> np.ndarray:
        """Batched `verify(...)["behavioural_deviation"]` for many (enrolled user, n-gesture window) pairs."""
        if not windows:
            return np.zeros(0)
        w = np.stack([self._z(g)[-n:] for g in windows])
        c = self.calib[n]
        e_lstm = _unit(self._lstm(w))
        e_lda = _unit(self._lda(n, w))
        p_lstm = np.stack([self.profiles[u][n]["lstm"] for u in user_ids])
        p_lda = np.stack([self.profiles[u][n]["lda"] for u in user_ids])
        s_lstm = (e_lstm * p_lstm).sum(1)
        s_lda = (e_lda * p_lda).sum(1)
        (m1, sd1), (m2, sd2) = c["norm"]["lstm"], c["norm"]["lda"]
        fused = ((s_lstm - m1) / sd1 + (s_lda - m2) / sd2) / 2
        return c["threshold"] - fused
