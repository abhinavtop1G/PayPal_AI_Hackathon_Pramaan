"""Verification protocol for fixed-password keystroke dynamics.

Open set: users are disjoint between train / valid / test. For each evaluated user a profile is built from enrolment
attempts; every later attempt by the same user is a genuine probe, every attempt by the other evaluated users is an
impostor probe. Scores are similarity matrices [probes, users] (higher = more like that user), so the EER code and
score fusion of the touch model (ml/models/biometrics/metrics.py) apply unchanged.

Scorers:
    cnn         cosine between the probe embedding and the mean enrolment embedding
    manhattan   scaled Manhattan (Killourhy & Maxion's best detector): -sum |x - mean| / mean-absolute-deviation
    mahalanobis -Mahalanobis distance with a shrunk covariance (Ledoit-Wolf)
"""
import numpy as np
from sklearn.covariance import LedoitWolf

from ml.models.biometrics.metrics import eer


def _unit(e):
    return e / np.linalg.norm(e, axis=-1, keepdims=True).clip(min=1e-12)


def profile_cnn(emb: np.ndarray) -> np.ndarray:
    return _unit(_unit(emb).mean(0))


def profile_manhattan(raw: np.ndarray, mad_floor: float = 0.005) -> tuple:
    mu = raw.mean(0)
    return mu, np.maximum(np.abs(raw - mu).mean(0), mad_floor)


def score_manhattan(raw: np.ndarray, prof: tuple) -> np.ndarray:
    mu, mad = prof
    return -(np.abs(raw - mu) / mad).sum(-1)


def profile_mahalanobis(raw: np.ndarray) -> tuple:
    lw = LedoitWolf().fit(raw)
    return raw.mean(0), lw.precision_


def score_mahalanobis(raw: np.ndarray, prof: tuple) -> np.ndarray:
    mu, prec = prof
    d = raw - mu
    return -np.sqrt(np.einsum("ij,jk,ik->i", d, prec, d).clip(min=0))


def sims(method: str, users, enrol_mask, probe_mask, user, raw=None, emb=None) -> np.ndarray:
    """[n_probes, len(users)] similarity of every probe row to every user's profile."""
    cols = []
    for u in users:
        e = enrol_mask & (user == u)
        if method == "cnn":
            cols.append(_unit(emb[probe_mask]) @ profile_cnn(emb[e]))
        elif method == "manhattan":
            cols.append(score_manhattan(raw[probe_mask], profile_manhattan(raw[e])))
        elif method == "mahalanobis":
            cols.append(score_mahalanobis(raw[probe_mask], profile_mahalanobis(raw[e])))
        else:
            raise ValueError(method)
    return np.stack(cols, 1)


def average_attempts(s: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean similarity over consecutive attempts sharing a group id (e.g. 3 tries in one sitting). Returns
    (sims [G, U], index of the first row of each group)."""
    _, first, inv = np.unique(groups, return_index=True, return_inverse=True)
    out = np.zeros((len(first), s.shape[1]))
    np.add.at(out, inv, s)
    return out / np.bincount(inv)[:, None], first


def score(s: np.ndarray, owner: np.ndarray) -> dict:
    """owner [P] = column index of each probe's true user."""
    gen = np.zeros_like(s, dtype=bool)
    gen[np.arange(len(owner)), owner] = True
    per_user = [eer(s[owner == j, j], s[owner != j, j]) for j in range(s.shape[1])]
    return {"eer": round(eer(s[gen], s[~gen]), 4), "per_user_eer_mean": round(float(np.mean(per_user)), 4),
            "n_users": int(s.shape[1]), "n_probes": int(len(owner))}


def norm_constants(s: np.ndarray) -> tuple[float, float]:
    return float(s.mean()), float(s.std() + 1e-12)
