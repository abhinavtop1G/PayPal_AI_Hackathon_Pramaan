"""Emerging-pattern radar: finds groups of accounts that behave abnormally *and* that the supervised payee
model does not explain, so a campaign that matches no known mule profile still surfaces as one case.

    1. fit an Isolation Forest on account-state snapshots from the reference period (unlabelled traffic)
    2. at each tick, keep accounts that are anomalous (score above a reference quantile) and unexplained
       (supervised risk below the flag threshold)
    3. group those that are close to each other (average-linkage, tighter than typical benign spread); a cluster of >= `min_cluster` accounts that persists is an "emerging pattern"
    4. an analyst names it; its confirmed accounts become labels for the next supervised model

The radar does not claim to know what the scam is. It tells the analyst that a coordinated group of
accounts has started behaving in a way nothing in the training data explains.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from .features import RADAR_FEATURES


@dataclass
class Emerging:
    cluster_id: str
    first_ts: float
    last_ts: float
    accounts: set = field(default_factory=set)
    ticks: int = 0
    max_size: int = 0
    confirmed_ts: float | None = None  # first tick at which the cluster had persisted `min_ticks` ticks


class Radar:
    def __init__(self, quantile: float = 0.997, min_cluster: int = 4, n_estimators: int = 200, seed: int = 0,
                 min_ticks: int = 2, tight: float = 0.5):
        self.quantile, self.min_cluster, self.min_ticks, self.tight = quantile, min_cluster, min_ticks, tight
        self.seed = seed
        self.pair_scale = 1.0
        self.iso = IsolationForest(n_estimators=n_estimators, random_state=seed, n_jobs=8)
        self.scaler = RobustScaler()
        self.fill: pd.Series | None = None
        self.threshold: float = np.inf

    def _prep(self, X: pd.DataFrame) -> np.ndarray:
        return self.scaler.transform(X[RADAR_FEATURES].fillna(self.fill))

    def fit(self, ref: pd.DataFrame) -> "Radar":
        self.fill = ref[RADAR_FEATURES].median()
        Z = self.scaler.fit_transform(ref[RADAR_FEATURES].fillna(self.fill))
        self.iso.fit(Z)
        sample = Z[np.random.default_rng(self.seed).choice(len(Z), min(600, len(Z)), replace=False)]
        d = np.sqrt(((sample[:, None, :] - sample[None, :, :]) ** 2).sum(-1))
        self.pair_scale = float(np.median(d[np.triu_indices(len(sample), 1)]))  # typical distance between two ordinary accounts
        self.threshold = float(np.quantile(self.anomaly_z(Z), self.quantile))
        return self

    def anomaly_z(self, Z: np.ndarray) -> np.ndarray:
        return -self.iso.score_samples(Z)

    def anomaly(self, X: pd.DataFrame) -> np.ndarray:
        return self.anomaly_z(self._prep(X))

    def candidates(self, X: pd.DataFrame, risk: np.ndarray, flag: float) -> np.ndarray:
        """Boolean mask: anomalous but not explained by the supervised model."""
        return (self.anomaly(X) >= self.threshold) & (risk < flag)

    def cluster(self, X: pd.DataFrame) -> np.ndarray:
        """Groups of accounts that are closer to each other than `tight` x the typical distance between ordinary
        accounts. Groups smaller than `min_cluster` are noise (-1). Small candidate sets are the norm here, where
        density-based methods are unstable, so this uses plain average-linkage with a distance cut."""
        if len(X) < self.min_cluster:
            return np.full(len(X), -1)
        lab = AgglomerativeClustering(n_clusters=None, distance_threshold=self.tight * self.pair_scale,
                                      linkage="average").fit_predict(self._prep(X))
        sizes = np.bincount(lab)
        out = np.full(len(lab), -1)
        for new, old in enumerate(np.flatnonzero(sizes >= self.min_cluster)):
            out[lab == old] = new
        return out

    def scan(self, snaps: pd.DataFrame, risk: np.ndarray, flag: float, start_ts: float = 0.0,
             jaccard: float = 0.3) -> list[Emerging]:
        """Walk the snapshot ticks in order and track clusters over time. `snaps` needs ts_s, account + features."""
        cand = self.candidates(snaps, risk, flag)
        live: dict[str, Emerging] = {}
        done: list[Emerging] = []
        n = 0
        for t, grp in snaps[cand & (snaps["ts_s"].to_numpy() >= start_ts)].groupby("ts_s", sort=True):
            labels = self.cluster(grp)
            groups = [set(grp["account"].to_numpy()[labels == k]) for k in sorted(set(labels) - {-1})]
            used = set()
            for g in groups:
                best = max(live.values(), key=lambda e: len(e.accounts & g) / len(e.accounts | g), default=None)
                if best is not None and best.cluster_id not in used and len(best.accounts & g) / len(best.accounts | g) >= jaccard:
                    best.accounts |= g
                    best.last_ts, best.ticks, best.max_size = float(t), best.ticks + 1, max(best.max_size, len(g))
                    if best.ticks == self.min_ticks:
                        best.confirmed_ts = float(t)
                    used.add(best.cluster_id)
                else:
                    n += 1
                    e = Emerging(f"EMG-{n:04d}", float(t), float(t), set(g), 1, len(g),
                                 float(t) if self.min_ticks <= 1 else None)
                    live[e.cluster_id] = e
                    used.add(e.cluster_id)
            stale = [k for k, e in live.items() if float(t) - e.last_ts > 24 * 3600]
            for k in stale:
                done.append(live.pop(k))
        done += live.values()
        return [e for e in done if e.ticks >= self.min_ticks]
