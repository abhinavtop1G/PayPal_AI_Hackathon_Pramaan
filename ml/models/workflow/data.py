"""Simulator sessions -> per-event feature tensors + labels for the workflow sequence model.

    python -m ml.models.workflow.data      # generate 50k sessions into data/sim_wf (if missing)

All features are observable at the moment of the event (session context so far, payee intel,
amount vs the user's own average, biometrics vs the user's own baseline, timing). Split by
session start time: days 0-60 train, 60-75 valid, 75-90 test.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ml.sim.generate import generate, save
from ml.sim.schema import BENIGN_TYPOLOGIES, SCAM_TYPOLOGIES, STAGE_ORDER, Ev

SIM_DIR = Path("data/sim_wf")
N_SESSIONS, SCAM_RATE, SEED = 50_000, 0.2, 11
SPLIT_DAYS = (60, 75)

EVENTS = [e.value for e in Ev]
CALLER = [None, "contact", "unknown", "voip_intl"]
SMS_SENDER = [None, "bank_shortcode", "unknown"]
APP_SOURCE = [None, "play_store", "sideload"]
STAGES = [s.value for s in sorted(STAGE_ORDER, key=STAGE_ORDER.get)]
TYPOLOGIES = SCAM_TYPOLOGIES + BENIGN_TYPOLOGIES
BIO = ["pressure", "swipe_velocity", "tap_interval_ms", "hesitation_ms", "orientation_var"]
CAT_COLS = {"event": EVENTS, "caller_kind": CALLER, "sms_sender_kind": SMS_SENDER, "app_source": APP_SOURCE}


@dataclass
class SeqData:
    num: list[np.ndarray]   # per session [T, F] float32
    cat: list[np.ndarray]   # per session [T, 4] int64 (event, caller, sms sender, app source)
    stage: list[np.ndarray]  # per session [T] int64
    is_payment: list[np.ndarray]  # per session [T] bool (PAYMENT_ATTEMPT = alert opportunity)
    ts: list[np.ndarray]    # per session [T] seconds from session start
    amount: list[np.ndarray]  # per session [T] payment amount (0 if none)
    sessions: pd.DataFrame  # one row per session, aligned with the lists
    num_names: list[str]


def ensure_sim() -> None:
    if not (SIM_DIR / "events.parquet").exists():
        save(SIM_DIR, *generate(N_SESSIONS, SCAM_RATE, SEED))


def _codes(series: pd.Series, vocab: list) -> np.ndarray:
    lookup = {v: i for i, v in enumerate(vocab)}
    return series.map(lambda v: lookup.get(None if pd.isna(v) else v, 0)).to_numpy("int64")


def featurise(events: pd.DataFrame, users: pd.DataFrame):
    e = events.merge(users, on="user_id", how="left")
    f = pd.DataFrame(index=e.index)
    for c in ["call_active", "call_video", "screen_share_active", "sideloaded_app_present", "accessibility_granted",
              "sms_has_link", "payee_is_merchant", "payee_is_new"]:
        f[c] = e[c].astype("float32").fillna(0)
    f["log_call_min"] = np.log1p(e["call_elapsed_s"].fillna(0) / 60)
    f["has_payee"] = e["payee_id"].notna().astype("float32")
    f["log_vpa_age"] = np.log1p(e["payee_vpa_age_days"].fillna(0))
    f["mule_score"] = e["payee_mule_score"].fillna(0)
    f["has_amount"] = e["amount"].notna().astype("float32")
    f["log_amt_vs_avg"] = np.log(e["amount"] / e["avg_txn_amount"]).fillna(0)
    f["has_bio"] = e["bio_hesitation_ms"].notna().astype("float32")
    for k in BIO:
        f[f"bio_{k}_vs_base"] = np.log(e[f"bio_{k}"] / e[f"bio_{k}_baseline"]).fillna(0)
    # real biometrics model (HMOG BiLSTM+LDA) deviation for this touch window; 0 when no window / no gestures
    f["bio_model_dev"] = (e["bio_model_dev"] if "bio_model_dev" in e else pd.Series(np.nan, index=e.index)).fillna(0)
    # telecom reputation (PSI, consented): the number on the active call has been reported to 1930
    rep = e["caller_reported"] if "caller_reported" in e else pd.Series(np.nan, index=e.index)
    f["caller_reported"] = rep.astype("float32").fillna(0)
    ts = e["ts"].to_numpy()
    first = ~e["session_id"].eq(e["session_id"].shift())
    f["log_dt_prev"] = np.log1p(np.where(first, 0, np.diff(ts, prepend=ts[0])).clip(min=0))
    f["log_t_session"] = np.log1p(ts)
    cat = np.stack([_codes(e[c], v) for c, v in CAT_COLS.items()], 1)
    return f.astype("float32"), cat


def as_seqdata(events: pd.DataFrame, sessions: pd.DataFrame, users: pd.DataFrame) -> SeqData:
    """All sessions of an event table as one SeqData (for evaluating on freshly generated or shifted data)."""
    events = events.sort_values(["session_id", "ts"], kind="stable").reset_index(drop=True)
    num, cat = featurise(events, users)
    stage = events["stage"].map({s: i for i, s in enumerate(STAGES)}).to_numpy("int64")
    is_pay = (events["event"] == Ev.PAYMENT_ATTEMPT.value).to_numpy()
    ts, amt = events["ts"].to_numpy("float64"), events["amount"].fillna(0).to_numpy("float64")
    sid = events["session_id"].to_numpy()
    bounds = np.flatnonzero(sid[1:] != sid[:-1]) + 1
    starts, ends = np.r_[0, bounds], np.r_[bounds, len(sid)]
    sess = sessions.set_index("session_id").loc[sid[starts]].reset_index()
    sess["typology_id"] = sess["typology"].map({t: i for i, t in enumerate(TYPOLOGIES)})
    N, r = num.to_numpy(), range(len(starts))
    return SeqData(num=[N[starts[i]:ends[i]] for i in r], cat=[cat[starts[i]:ends[i]] for i in r],
                   stage=[stage[starts[i]:ends[i]] for i in r], is_payment=[is_pay[starts[i]:ends[i]] for i in r],
                   ts=[ts[starts[i]:ends[i]] for i in r], amount=[amt[starts[i]:ends[i]] for i in r], sessions=sess,
                   num_names=list(num.columns))


def load(split_days=SPLIT_DAYS) -> dict[str, SeqData]:
    ensure_sim()
    events = pd.read_parquet(SIM_DIR / "events.parquet")
    sessions = pd.read_parquet(SIM_DIR / "sessions.parquet")
    users = pd.read_parquet(SIM_DIR / "users.parquet")
    num, cat = featurise(events, users)
    stage = events["stage"].map({s: i for i, s in enumerate(STAGES)}).to_numpy("int64")
    is_pay = (events["event"] == Ev.PAYMENT_ATTEMPT.value).to_numpy()
    ts = events["ts"].to_numpy("float64")
    amt = events["amount"].fillna(0).to_numpy("float64")

    sid = events["session_id"].to_numpy()
    bounds = np.flatnonzero(sid[1:] != sid[:-1]) + 1
    starts, ends = np.r_[0, bounds], np.r_[bounds, len(sid)]
    order = pd.Index(sessions["session_id"]).get_indexer(sid[starts])
    sess = sessions.iloc[order].reset_index(drop=True)
    sess["typology_id"] = sess["typology"].map({t: i for i, t in enumerate(TYPOLOGIES)})
    day = (sess["start_time"] - sess["start_time"].min()).dt.total_seconds() / 86400
    part = np.select([day < split_days[0], day < split_days[1]], ["train", "valid"], "test")

    N, C = num.to_numpy(), cat
    out = {}
    for name in ("train", "valid", "test"):
        idx = np.flatnonzero(part == name)
        out[name] = SeqData(
            num=[N[starts[i]:ends[i]] for i in idx], cat=[C[starts[i]:ends[i]] for i in idx],
            stage=[stage[starts[i]:ends[i]] for i in idx], is_payment=[is_pay[starts[i]:ends[i]] for i in idx],
            ts=[ts[starts[i]:ends[i]] for i in idx], amount=[amt[starts[i]:ends[i]] for i in idx], sessions=sess.iloc[idx].reset_index(drop=True),
            num_names=list(num.columns),
        )
    return out


if __name__ == "__main__":
    d = load()
    for k, v in d.items():
        s = v.sessions
        print(f"{k}: {len(s):,} sessions, scam rate {s['is_scam'].mean():.3f}, events {sum(len(x) for x in v.num):,}, "
              f"max len {max(len(x) for x in v.num)}; scam mix {s[s.is_scam].typology.value_counts(normalize=True).round(2).to_dict()}")
