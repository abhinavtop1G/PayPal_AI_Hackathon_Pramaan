"""Verification protocol and EER for continuous authentication."""
import numpy as np
from sklearn.metrics import roc_curve

from .windows import ENROL_SESSIONS


def eer(genuine: np.ndarray, impostor: np.ndarray) -> float:
    """Equal error rate: the operating point where false-accept rate == false-reject rate."""
    y = np.r_[np.ones(len(genuine)), np.zeros(len(impostor))]
    fpr, tpr, _ = roc_curve(y, np.r_[genuine, impostor])
    fnr = 1 - tpr
    i = np.nanargmin(np.abs(fnr - fpr))
    return float((fpr[i] + fnr[i]) / 2)


def _unit(e):
    return e / np.linalg.norm(e, axis=-1, keepdims=True).clip(min=1e-12)


def similarity(emb: np.ndarray, user: np.ndarray, session: np.ndarray):
    """Profile = mean embedding of each user's enrolment-session windows; probes = later sessions.
    Returns (sims [P, U], owner [P] = column of each probe's true user, probe mask over windows)."""
    emb = _unit(emb)
    enrol = np.isin(session, list(ENROL_SESSIONS))
    users = np.unique(user)
    profiles = np.stack([_unit(emb[enrol & (user == u)].mean(0)) for u in users])
    probe = ~enrol
    return emb[probe] @ profiles.T, np.searchsorted(users, user[probe]), probe


def score(sims: np.ndarray, owner: np.ndarray, scenario_probe: np.ndarray | None = None) -> dict:
    """Genuine = own probes vs own profile; impostor = every other user's probes vs that profile."""
    is_gen = np.zeros_like(sims, dtype=bool)
    is_gen[np.arange(len(owner)), owner] = True
    out = {"eer": eer(sims[is_gen], sims[~is_gen]),
           "per_user_eer_mean": float(np.mean([eer(sims[owner == j, j], sims[owner != j, j]) for j in range(sims.shape[1])])),
           "n_users": int(sims.shape[1]), "n_probe_windows": int(len(owner))}
    if scenario_probe is not None:
        for code, name in ((1, "sitting"), (2, "walking")):
            rows = scenario_probe == code
            if rows.any():
                out[f"eer_{name}"] = eer(sims[rows][is_gen[rows]], sims[rows][~is_gen[rows]])
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def verify(emb: np.ndarray, user: np.ndarray, session: np.ndarray, scenario: np.ndarray | None = None) -> dict:
    sims, owner, probe = similarity(emb, user, session)
    return score(sims, owner, None if scenario is None else scenario[probe])


def fuse(*sims: np.ndarray) -> np.ndarray:
    """Average of globally z-normalised similarity matrices (score-level fusion)."""
    return np.mean([(s - s.mean()) / (s.std() + 1e-12) for s in sims], axis=0)
