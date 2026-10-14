"""Causal feature engineering for IEEE-CIS.

Every engineered feature uses only transactions *before* the current one (data is sorted by
TransactionDT), so the same features can be computed online at transaction time.

Pseudo-user id ("uid") = card1 + addr1 + account-start day (TransactionDay - D1), the standard
IEEE-CIS client proxy.
"""
import numpy as np
import pandas as pd

from .data import CATEGORICAL

DROP = ["TransactionID", "isFraud", "TransactionDT"]
UID_AGG_COLS = ["C1", "C2", "C5", "C11", "C13", "C14", "D2", "D3", "dist1"]


def _group_codes(keys: list[pd.Series]) -> pd.Series:
    return pd.Series(pd.MultiIndex.from_arrays(keys).factorize()[0])  # NaN keys -> own code (-1 groups together)


def _prior_count_in_window(groups: np.ndarray, t: np.ndarray, window: int) -> np.ndarray:
    """For each row, number of earlier rows in the same group within `window` seconds."""
    order = np.lexsort((t, groups))
    key = (groups[order].astype(np.int64) + 1) * 10**9 + t[order]
    cnt_sorted = np.arange(len(key)) - np.searchsorted(key, key - window, side="left")
    out = np.empty_like(cnt_sorted)
    out[order] = cnt_sorted
    return out


def _is_first(keys: list[pd.Series], present: pd.Series) -> pd.Series:
    """1 if this key combination has not been seen before; NaN where the value is missing."""
    first = (pd.DataFrame({i: k for i, k in enumerate(keys)}).groupby(list(range(len(keys))), dropna=False, sort=False)
             .cumcount() == 0).astype("float32")
    return first.where(present)


def build_features(df: pd.DataFrame):
    """Returns X (features), y (labels), amount, uid (client group code, for post-processing; not a feature)."""
    t = df["TransactionDT"].to_numpy()
    amt = df["TransactionAmt"]
    day = t // 86400
    new = {}

    # ---- transaction shape / time ----
    new["hour"] = ((t // 3600) % 24).astype("int8")
    new["dow"] = (day % 7).astype("int8")
    new["amt_log"] = np.log1p(amt).astype("float32")
    new["amt_cents"] = (amt - np.floor(amt)).round(3).astype("float32")

    # ---- pseudo-user id ----
    uid = _group_codes([df["card1"], df["addr1"], pd.Series(day) - df["D1"]])
    card1 = _group_codes([df["card1"]])
    g_uid = amt.groupby(uid, sort=False)

    # ---- user history (strictly prior) ----
    prior_n = g_uid.cumcount().to_numpy()
    prior_sum = g_uid.cumsum().to_numpy() - amt.to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        prior_mean = np.where(prior_n > 0, prior_sum / np.maximum(prior_n, 1), np.nan)
    new["uid_prior_cnt"] = prior_n.astype("float32")
    new["uid_prior_amt_mean"] = prior_mean.astype("float32")
    new["amt_to_uid_mean"] = (amt.to_numpy() / prior_mean).astype("float32")
    new["uid_secs_since_prev"] = (df["TransactionDT"] - df["TransactionDT"].groupby(uid).shift(1)).astype("float32")

    # ---- velocity ----
    for w, name in [(3600, "1h"), (86400, "24h"), (7 * 86400, "7d")]:
        new[f"uid_cnt_{name}"] = _prior_count_in_window(uid.to_numpy(), t, w).astype("float32")
    new["card1_cnt_24h"] = _prior_count_in_window(card1.to_numpy(), t, 86400).astype("float32")

    # ---- device / identity / geo novelty ----
    novelty = {
        "uid_new_device": ([uid, df["DeviceInfo"]], df["DeviceInfo"], uid),
        "uid_new_email": ([uid, df["P_emaildomain"]], df["P_emaildomain"], uid),
        "uid_new_browser": ([uid, df["id_31"]], df["id_31"], None),
        "card1_new_addr": ([card1, df["addr1"]], df["addr1"], card1),  # geolocation jump
    }
    for name, (keys, val, distinct_by) in novelty.items():
        flag = _is_first(keys, val.notna())
        new[name] = flag.to_numpy()
        if distinct_by is not None:
            new[name.replace("_new_", "_n_distinct_")] = flag.fillna(0).groupby(distinct_by).cumsum().to_numpy("float32")

    # ---- D normalisation: "days since X" -> day on which X happened (stable per client over time) ----
    for c in ["D4", "D10", "D15"]:
        new[f"{c}n"] = (day - df[c]).astype("float32").to_numpy()

    # ---- causal frequency encoding: how often has this value been seen before ----
    for c in ["card1", "card2", "addr1", "P_emaildomain"]:
        new[f"{c}_prior_freq"] = df.groupby(c, dropna=False, sort=False).cumcount().to_numpy("float32")

    # ---- client profile: expanding mean over the uid's *prior* transactions, and deviation from it ----
    agg_src = {c: df[c] for c in UID_AGG_COLS if c in df.columns}
    agg_src.update({c: pd.Series(new[c], index=df.index) for c in ["D4n", "D10n", "D15n"]})
    for c, v in agg_src.items():
        present = v.notna().astype("float64")
        filled = v.fillna(0).astype("float64")
        s = filled.groupby(uid).cumsum() - filled
        n = present.groupby(uid).cumsum() - present
        mean = (s / n.where(n > 0)).astype("float32")
        new[f"uid_{c}_prior_mean"] = mean.to_numpy()
        new[f"{c}_minus_uid_mean"] = (v.astype("float32") - mean).to_numpy()

    y = df["isFraud"].to_numpy()
    X = pd.concat([df.drop(columns=DROP), pd.DataFrame(new, index=df.index)], axis=1)
    for c in CATEGORICAL:
        X[c] = X[c].astype("category")
    return X, y, amt.to_numpy("float64"), uid.to_numpy()
