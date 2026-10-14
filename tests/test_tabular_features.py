import numpy as np
import pandas as pd

from ml.models.tabular.data import CATEGORICAL
from ml.models.tabular.features import build_features


def _toy(n=400, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.sort(rng.integers(86400, 86400 * 20, n))
    d = t // 86400
    df = pd.DataFrame({
        "TransactionID": np.arange(n), "isFraud": rng.integers(0, 2, n).astype("int8"),
        "TransactionDT": t, "TransactionAmt": rng.lognormal(4, 1, n).astype("float32"),
        "card1": rng.integers(1000, 1010, n).astype("float32"),
        "card2": rng.choice([111.0, 222.0, np.nan], n).astype("float32"),
        "addr1": rng.choice([100.0, 200.0, np.nan], n).astype("float32"),
        "dist1": rng.choice([5.0, 50.0, np.nan], n).astype("float32"),
        **{c: rng.integers(0, 5, n).astype("float32") for c in ["C1", "C2", "C5", "C11", "C13", "C14"]},
        **{c: (d - rng.integers(0, 3, n)).astype("float32") for c in ["D1", "D2", "D3", "D4", "D10", "D15"]},
    })
    df.loc[rng.random(n) < 0.2, "D4"] = np.nan  # missing values must not break the expanding means
    for c in CATEGORICAL:
        df[c] = pd.Series(rng.choice(["a", "b", None], n), dtype="string")
    return df


def _engineered(X: pd.DataFrame, raw: pd.DataFrame) -> list[str]:
    return [c for c in X.columns if c not in raw.columns]


def test_features_are_causal():
    """Dropping future rows must not change any engineered feature of earlier rows."""
    df = _toy()
    full, _, _, _ = build_features(df.copy())
    cut = 250
    part, _, _, _ = build_features(df.iloc[:cut].copy())
    cols = _engineered(full, df)
    assert len(cols) >= 40
    pd.testing.assert_frame_equal(full[cols].iloc[:cut].reset_index(drop=True), part[cols].reset_index(drop=True))


def test_label_not_in_features():
    X, y, amt, uid = build_features(_toy())
    assert "isFraud" not in X.columns and "TransactionDT" not in X.columns
    assert len(X) == len(y) == len(amt) == len(uid)


def test_prior_count_window():
    X, _, _, _ = build_features(_toy())
    assert (X["uid_cnt_1h"] <= X["uid_cnt_24h"]).all() and (X["uid_cnt_24h"] <= X["uid_cnt_7d"]).all()
    assert (X["uid_cnt_7d"] <= X["uid_prior_cnt"]).all()


def test_uid_prior_mean_matches_bruteforce():
    df = _toy()
    X, _, _, uid = build_features(df.copy())
    for i in [10, 120, 399]:
        prev = df["C13"].to_numpy()[:i][uid[:i] == uid[i]]
        expected = prev.mean() if len(prev) else np.nan
        np.testing.assert_allclose(X["uid_C13_prior_mean"].iloc[i], expected, rtol=1e-5, equal_nan=True)
