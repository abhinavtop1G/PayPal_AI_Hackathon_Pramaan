import numpy as np
import pandas as pd
import pytest

from ml.sim.generate import generate, generate_demo
from ml.sim.schema import BENIGN_TYPOLOGIES, EVENT_COLUMNS, SCAM_TYPOLOGIES, STAGE_ORDER, Stage


@pytest.fixture(scope="module")
def data():
    return generate(n_sessions=1500, scam_rate=0.3, seed=1)


def test_schema(data):
    events, sessions, users, payees = data
    assert list(events.columns) == EVENT_COLUMNS
    assert len(sessions) == 1500
    assert sessions["is_scam"].sum() == 450
    assert set(sessions["typology"]) == set(SCAM_TYPOLOGIES + BENIGN_TYPOLOGIES)
    assert sessions["n_events"].sum() == len(events)


def test_deterministic():
    a = generate(n_sessions=200, seed=5)[0]
    b = generate(n_sessions=200, seed=5)[0]
    pd.testing.assert_frame_equal(a, b)


def test_timestamps_strictly_increase(data):
    events = data[0]
    assert events.groupby("session_id")["ts"].apply(lambda s: s.is_monotonic_increasing and s.is_unique).all()


def test_scam_stages_monotonic_and_benign_none(data):
    events, sessions = data[0], data[1]
    scam_ids = set(sessions.loc[sessions["is_scam"], "session_id"])
    order = events["stage"].map({s.value: o for s, o in STAGE_ORDER.items()})
    is_scam_ev = events["session_id"].isin(scam_ids)
    assert (events.loc[~is_scam_ev, "stage"] == Stage.NONE.value).all()
    mono = order[is_scam_ev].groupby(events.loc[is_scam_ev, "session_id"]).apply(lambda s: s.is_monotonic_increasing)
    assert mono.all()  # 'none' (pre-contact background activity) may only appear before the scam starts
    reached = events[is_scam_ev].groupby("session_id")["stage"].agg(set)
    assert reached.apply(lambda st: {"contact", "extraction"} <= st).all()


def test_no_class_exclusive_cues(data):
    """Every event type / SMS sender / install source seen in scams must also occur in benign sessions,
    otherwise a sequence model can 'detect' scams from a single token."""
    events, sessions = data[0], data[1]
    scam = events["session_id"].isin(set(sessions.loc[sessions["is_scam"], "session_id"]))
    for col in ["event", "sms_sender_kind", "app_source"]:
        missing = set(events.loc[scam, col].dropna()) - set(events.loc[~scam, col].dropna())
        assert not missing, f"{col} values only in scams: {missing}"
    assert events.loc[~scam & events["accessibility_granted"].astype(bool)].shape[0] > 0


def test_extraction_ts_is_first_extraction_attempt(data):
    events, sessions = data[0], data[1]
    attempts = events[(events["event"] == "PAYMENT_ATTEMPT") & (events["stage"] == "extraction")]
    first = attempts.groupby("session_id")["ts"].min()
    scams = sessions[sessions["is_scam"]].set_index("session_id")
    assert scams["extraction_ts"].notna().all()
    np.testing.assert_allclose(scams.loc[first.index, "extraction_ts"], first)
    assert (scams["loss_amount"] > 0).all()
    assert sessions.loc[~sessions["is_scam"], "extraction_ts"].isna().all()
    assert (sessions.loc[~sessions["is_scam"], "loss_amount"] == 0).all()


def test_call_context_consistent(data):
    events = data[0]
    on_call = events[events["call_active"].astype(bool)]
    assert on_call["caller_kind"].notna().all() and on_call["call_elapsed_s"].ge(0).all()
    off_call = events[~events["call_active"].astype(bool)]
    assert off_call["caller_kind"].isna().all() and off_call["call_elapsed_s"].isna().all()


def test_mules_reused_across_victims(data):
    events, sessions, _, payees = data
    mule_ids = set(payees.loc[payees["is_mule"], "payee_id"])
    pays = events[(events["event"] == "PAYMENT_SUCCESS") & events["payee_id"].isin(mule_ids)]
    victims_per_mule = pays.groupby("payee_id")["user_id"].nunique()
    assert victims_per_mule.max() >= 5  # fan-in structure exists for the GNN
    # benign sessions never pay mules
    benign_ids = set(sessions.loc[~sessions["is_scam"], "session_id"])
    assert not pays["session_id"].isin(benign_ids).any()


def test_signals_overlap_between_classes(data):
    """Guard against a trivially separable dataset: benign sessions must also contain scam-like cues."""
    events, sessions = data[0], data[1]
    benign_ids = set(sessions.loc[~sessions["is_scam"], "session_id"])
    att = events[(events["event"] == "PAYMENT_ATTEMPT") & events["session_id"].isin(benign_ids)]
    risky_benign = att[att["call_active"].astype(bool) & (att["caller_kind"] == "unknown") & att["payee_is_new"].astype(bool)]
    assert len(risky_benign) > 20


def test_demo_session():
    events, sessions, _, _ = generate_demo("digital_arrest")
    s = sessions.iloc[0]
    assert s["is_scam"] and s["difficulty"] == 0.0
    assert list(events["stage"].drop_duplicates()) == ["contact", "pretext", "isolation", "extraction"]
    first_pay = events[events["event"] == "PAYMENT_ATTEMPT"].iloc[0]
    assert bool(first_pay["call_active"]) and first_pay["payee_is_new"]
    assert generate_demo("family_transfer")[1].iloc[0]["is_scam"] == False  # noqa: E712
