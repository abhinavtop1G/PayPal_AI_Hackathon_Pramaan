"""Replace the simulator's label-derived `payee_mule_score` with the honest payee-risk score.

    python -m ml.campaign.attach --sim data/sim_wf            # rewrites events.parquet (original kept as events_standin.parquet)

The workflow GRU and the fusion model read `payee_mule_score`. In the simulator that column was drawn from the
ground truth with noise. This script builds the payee-side ledger for the same simulated world, scores every
payment with the causal payee model (out-of-fold for the training period) and writes those scores back, so the
session models are retrained against a payee signal that can be wrong in realistic ways.

After attaching, retrain the downstream models:
    python -m ml.models.workflow.train --seed 0 && python -m ml.engine.oof && python -m ml.engine.fit
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ml.sim.generate import START

from .features import FEATURES, stream_features
from .ledger import build_ledger
from .payee_model import fit


def attach(events: pd.DataFrame, sessions: pd.DataFrame, users: pd.DataFrame, payees: pd.DataFrame, seed: int = 13):
    ledger = build_ledger(events, sessions, users, payees, seed=seed, novel=False)
    tr, ac = ledger.transfers, ledger.accounts
    res = stream_features(tr, ac)
    c = res.credit
    t = tr.loc[c.index]
    accts = ac.set_index("account")
    day = t["ts_s"] / 86400.0
    active = tr[tr["scam_credit"] | tr["kind"].isin(["forward"])].groupby("dst")["ts_s"].min()
    y = (t["dst"].map(accts["is_mule"]) & (t["ts_s"] >= t["dst"].map(active))).astype(int)
    _, risk = fit(c[FEATURES], y, day, t["dst"])  # out-of-fold for the training period
    allc = pd.DataFrame({"session_id": t["session_id"].to_numpy(), "payee_id": t["dst"].to_numpy(), "ts_s": t["ts_s"].to_numpy(),
                         "risk": risk}).sort_values("ts_s")
    scored = allc[allc["session_id"].notna()]
    ev = events.copy()
    ev["ts_s"] = (ev["event_time"] - START).dt.total_seconds()
    ev = ev.sort_values("ts_s", kind="stable")
    new = ev["payee_mule_score"].copy()
    # payments: the attempt / payee-add rows take the score of the success that follows within seconds
    pay_rows = ev["event"].isin(["PAYEE_ADD", "PAYMENT_ATTEMPT", "PAYMENT_SUCCESS"])
    left = ev[pay_rows][["ts_s", "session_id", "payee_id"]].reset_index()
    m = pd.merge_asof(left.sort_values("ts_s"), scored, on="ts_s", by=["session_id", "payee_id"], direction="forward", tolerance=3600.0)
    ok = m["risk"].notna()
    new.loc[m.loc[ok, "index"].to_numpy()] = m.loc[ok, "risk"].to_numpy()
    # payouts from a payee (CREDIT_RECEIVED): the payee's latest scored credit before that moment, else the benign median
    cred = ev[ev["event"] == "CREDIT_RECEIVED"][["ts_s", "payee_id"]].reset_index()
    if len(cred):
        mc = pd.merge_asof(cred.sort_values("ts_s"), allc[["payee_id", "ts_s", "risk"]], on="ts_s", by="payee_id", direction="backward")
        fill = float(np.median(risk[(y == 0).to_numpy()]))
        new.loc[mc["index"].to_numpy()] = mc["risk"].fillna(fill).to_numpy()
    out = events.copy()
    out["payee_mule_score"] = new.reindex(out.index).astype("float64")
    return out, float(ok.mean())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", type=Path, default=Path("data/sim_wf"))
    a = ap.parse_args()
    ev, se, us, pa = (pd.read_parquet(a.sim / f"{n}.parquet") for n in ("events", "sessions", "users", "payees"))
    if "syndicate" not in pa:
        raise SystemExit("this simulator output predates syndicates; regenerate it with `python -m ml.models.workflow.data`")
    backup = a.sim / "events_standin.parquet"
    if not backup.exists():
        ev.to_parquet(backup, index=False)
    new, cover = attach(ev, se, us, pa)
    new.to_parquet(a.sim / "events.parquet", index=False)
    pay = new[new["event"] == "PAYMENT_ATTEMPT"].merge(pa[["payee_id", "is_mule"]], on="payee_id")
    print(f"rewrote payee_mule_score on {cover:.1%} of payment rows; mean score mule {pay.loc[pay.is_mule, 'payee_mule_score'].mean():.3f} "
          f"vs other {pay.loc[~pay.is_mule, 'payee_mule_score'].mean():.3f}")


if __name__ == "__main__":
    main()
