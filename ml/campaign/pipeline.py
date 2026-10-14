"""Build the whole payee-side stack once: simulate -> ledger -> causal features -> payee model -> honest scores.

    from ml.campaign.pipeline import build
    b = build(n_sessions=10_000)

"Honest" means: scores for the training period come from account-grouped out-of-fold models, scores for
later periods from the model trained on the training period only. Nothing is scored by a model that saw
that account's rows, so the scores can safely feed a downstream model (the session fusion).
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ml.sim.generate import generate

from .features import FEATURES, StreamResult, stream_features
from .ledger import DAY, Ledger, build_ledger
from .payee_model import PayeeRiskModel, fit

SPLIT_DAYS = (60, 75)


@dataclass
class Bundle:
    ledger: Ledger
    stream: StreamResult
    credit: pd.DataFrame      # one row per scoreable credit: features + labels + honest `risk`
    snaps: pd.DataFrame       # periodic account-state snapshots with `risk` (model trained on the training period)
    src_snap: pd.DataFrame
    model: PayeeRiskModel
    sim: tuple                # (events, sessions, users, payees)
    split_days: tuple


def build(n_sessions: int = 10_000, seed: int = 7, ledger_seed: int = 13, tick_hours: float | None = 4.0,
          split_days: tuple = SPLIT_DAYS, novel: bool = True, verbose: bool = True) -> Bundle:
    log = print if verbose else (lambda *a, **k: None)
    sim = generate(n_sessions, 0.2, seed)
    ledger = build_ledger(*sim, seed=ledger_seed, novel=novel)
    tr, ac = ledger.transfers, ledger.accounts
    log(f"ledger: {len(tr):,} transfers, {len(ac):,} accounts")
    stream = stream_features(tr, ac, tick_hours=tick_hours)
    accts = ac.set_index("account")
    c = stream.credit.copy()
    t = tr.loc[c.index]
    c["ts_s"], c["day"] = t["ts_s"].to_numpy(), t["ts_s"].to_numpy() / DAY
    c["src"], c["dst"], c["amount"], c["kind"] = t["src"].to_numpy(), t["dst"].to_numpy(), t["amount"].to_numpy(), t["kind"].to_numpy()
    c["scam_credit"], c["standin_score"] = t["scam_credit"].to_numpy(), t["standin_score"].to_numpy()
    c["dst_kind"] = c["dst"].map(accts["kind"])
    # label: a mule account is positive from its first scam-related credit on. Its earlier ordinary-looking credits
    # are negatives, so the model cannot win by recognising the account's identity.
    active = tr[tr["scam_credit"] | tr["kind"].isin(["forward", "novel_collect"])].groupby("dst")["ts_s"].min()
    first_active = c["dst"].map(active)
    c["y"] = (c["dst"].map(accts["is_mule"]) & (c["ts_s"] >= first_active)).astype(int)
    c["is_novel"] = c["dst"].map(accts["is_novel"]).astype(bool)
    c["truth"] = c["dst"].map(accts["campaign_truth"])
    log(f"credit rows: {len(c):,}, mule share {c['y'].mean():.1%}")
    model, risk = fit(c[FEATURES], c["y"], c["day"], c["dst"], split_days=split_days)
    c["risk"] = risk
    s = stream.snapshots.copy()
    if len(s):
        s["risk"] = model.predict(s)
    ss = stream.src_snap.copy()
    if len(ss):
        ss["risk"] = model.predict(ss)
    return Bundle(ledger, stream, c, s, ss, model, sim, tuple(split_days))


def save_ledger(ledger: Ledger, out: Path) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ledger.transfers.to_parquet(out / "transfers.parquet", index=False)
    ledger.accounts.to_parquet(out / "accounts.parquet", index=False)


def load_ledger(out: Path) -> Ledger:
    out = Path(out)
    return Ledger(pd.read_parquet(out / "transfers.parquet"), pd.read_parquet(out / "accounts.parquet"))
