"""IBM AML (HI-Small) -> time-ordered edge tensors for the temporal GNN, cached as .npz.

Edges are sorted by timestamp (stable), so edge index order is a valid causal order: an edge may
only look at edges with a smaller index. Split = chronological 60/20/20 by edge, as in IBM's
AML benchmark.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("DATA/HI-Small_Trans.csv")
CACHE = Path("DATA/aml/hi_small_edges.npz")
COLS = ["ts", "from_bank", "from_acct", "to_bank", "to_acct", "amt_recv", "cur_recv", "amt_paid", "cur_paid", "fmt", "label"]

# numeric edge features (order matters; see EDGE_NUM_NAMES)
EDGE_NUM_NAMES = ["log_amt_paid", "log_amt_recv", "cross_currency", "self_loop", "same_bank", "hour_sin", "hour_cos"]


@dataclass
class AMLGraph:
    src: np.ndarray        # [E] int64 node id
    dst: np.ndarray        # [E] int64
    t: np.ndarray          # [E] int64 minutes since start
    x_num: np.ndarray      # [E, len(EDGE_NUM_NAMES)] float32
    cur_paid: np.ndarray   # [E] int64 category id
    cur_recv: np.ndarray   # [E] int64
    fmt: np.ndarray        # [E] int64
    y: np.ndarray          # [E] int8
    n_nodes: int
    n_cur: int
    n_fmt: int

    @property
    def n_edges(self) -> int:
        return len(self.y)

    def splits(self, train=0.6, valid=0.2):
        e = self.n_edges
        a, b = int(e * train), int(e * (train + valid))
        return np.arange(a), np.arange(a, b), np.arange(b, e)


def _build(raw: Path) -> dict:
    df = pd.read_csv(raw, header=0, names=COLS, dtype={"from_bank": str, "to_bank": str, "from_acct": str, "to_acct": str})
    df["ts"] = pd.to_datetime(df["ts"], format="%Y/%m/%d %H:%M")
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)

    src_key = df["from_bank"] + "_" + df["from_acct"]
    dst_key = df["to_bank"] + "_" + df["to_acct"]
    codes, uniques = pd.factorize(pd.concat([src_key, dst_key], ignore_index=True))
    e = len(df)
    cur_codes, cur_uni = pd.factorize(pd.concat([df["cur_paid"], df["cur_recv"]], ignore_index=True))
    fmt_codes, fmt_uni = pd.factorize(df["fmt"])

    minutes = ((df["ts"] - df["ts"].min()).dt.total_seconds() // 60).astype("int64").to_numpy()
    hour = df["ts"].dt.hour.to_numpy() + df["ts"].dt.minute.to_numpy() / 60
    x_num = np.column_stack([
        np.log1p(df["amt_paid"].to_numpy()),
        np.log1p(df["amt_recv"].to_numpy()),
        (df["cur_paid"] != df["cur_recv"]).to_numpy(),
        (src_key == dst_key).to_numpy(),
        (df["from_bank"] == df["to_bank"]).to_numpy(),
        np.sin(2 * np.pi * hour / 24),
        np.cos(2 * np.pi * hour / 24),
    ]).astype("float32")
    return dict(
        src=codes[:e].astype("int64"), dst=codes[e:].astype("int64"), t=minutes, x_num=x_num,
        cur_paid=cur_codes[:e].astype("int64"), cur_recv=cur_codes[e:].astype("int64"), fmt=fmt_codes.astype("int64"),
        y=df["label"].to_numpy("int8"), n_nodes=np.int64(len(uniques)), n_cur=np.int64(len(cur_uni)),
        n_fmt=np.int64(len(fmt_uni)),
    )


VOCAB = Path("DATA/aml/hi_small_vocab.npz")


def load_vocab(raw: Path = RAW, cache: Path = VOCAB) -> dict:
    """Account / currency / payment-format ids exactly as `_build` assigns them, plus the time origin.
    Needed to score new transfers by account name (serving)."""
    if not cache.exists():
        df = pd.read_csv(raw, header=0, names=COLS, usecols=range(len(COLS)),
                         dtype={"from_bank": str, "to_bank": str, "from_acct": str, "to_acct": str})
        df["ts"] = pd.to_datetime(df["ts"], format="%Y/%m/%d %H:%M")
        df = df.sort_values("ts", kind="stable").reset_index(drop=True)
        keys = pd.concat([df["from_bank"] + "_" + df["from_acct"], df["to_bank"] + "_" + df["to_acct"]], ignore_index=True)
        _, accounts = pd.factorize(keys)
        _, currencies = pd.factorize(pd.concat([df["cur_paid"], df["cur_recv"]], ignore_index=True))
        _, formats = pd.factorize(df["fmt"])
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, accounts=np.asarray(accounts, dtype=str), currencies=np.asarray(currencies, dtype=str),
                 formats=np.asarray(formats, dtype=str), t0=np.datetime64(df["ts"].min(), "m"))
    z = np.load(cache)
    return {"accounts": z["accounts"], "currencies": [str(c) for c in z["currencies"]], "formats": [str(f) for f in z["formats"]],
            "t0": pd.Timestamp(z["t0"].item())}


def load_aml(raw: Path = RAW, cache: Path = CACHE, refresh: bool = False) -> AMLGraph:
    if not cache.exists() or refresh:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, **_build(raw))
    z = np.load(cache)
    return AMLGraph(**{k: (int(z[k]) if z[k].ndim == 0 else z[k]) for k in z.files})
