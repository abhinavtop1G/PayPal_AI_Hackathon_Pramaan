"""New session signals: real HMOG gestures, telecom caller reputation (PSI + consent), adaptive-scammer knobs."""
from pathlib import Path

import numpy as np
import pytest

from backend.context import ContextTracker
from infra.privacy.reputation import ReputationClient, Telecom
from ml.sim import telecom
from ml.sim.generate import generate
from ml.sim.schema import SCAM_TYPOLOGIES

HMOG = Path("DATA/hmog/gestures.parquet")
needs_hmog = pytest.mark.skipif(not HMOG.exists(), reason="needs the HMOG gesture cache")


# ---------------------------------------------------------------- gesture bank
@needs_hmog
def test_bank_uses_only_held_out_users_and_probe_sessions():
    from ml.models.biometrics.windows import ENROL_SESSIONS, split_users
    from ml.sim.hmog_bank import HmogBank, seeded_rng
    import pandas as pd
    bank = HmogBank.load()
    users = pd.read_parquet(HMOG, columns=["user"])["user"].unique()
    train, valid, test = split_users(users, 0)
    assert set(bank.subjects) == {int(u) for u in test} and not set(bank.subjects) & {int(u) for u in train | valid}
    rng = seeded_rng("t")
    for prof in ("normal", "coerced", "remote"):
        for _ in range(50):
            owner, source, session, *_ = bank.window_ref(bank.subjects[3], prof, 1.0, rng).split("|")
            assert int(session) not in ENROL_SESSIONS                      # probes never come from enrolment sessions
            assert (source != owner) == (prof == "remote")                 # only 'remote' is someone else's hands
    ref = bank.window_ref(bank.subjects[0], "coerced", 0.7, rng)
    assert bank.resolve(ref) == bank.resolve(ref) and len(bank.resolve(ref)[1]) == 10  # reproducible


@needs_hmog
def test_offline_scorer_matches_api_verify():
    torch = pytest.importorskip("torch")
    if not Path("ml/models/biometrics/artifacts/hmog_bilstm.pt").exists():
        pytest.skip("needs the biometrics artifact")
    from ml.models.biometrics.scorer import BioScorer
    from ml.sim.hmog_bank import HmogBank, seeded_rng
    bank = HmogBank.load()
    s = BioScorer("cuda" if torch.cuda.is_available() else "cpu")
    s.enroll("hmog:x", bank.enrolment(bank.subjects[0]))
    refs = [bank.window_ref(bank.subjects[0], p, 1.0, seeded_rng("p", p)) for p in ("normal", "remote")]
    windows = [bank.resolve(r)[1] for r in refs]
    batched = s.deviation_many(["hmog:x"] * 2, windows)
    single = [s.verify("hmog:x", w)["behavioural_deviation"] for w in windows]
    assert np.allclose(batched, single, atol=1e-3)


# ---------------------------------------------------------------- telecom reputation
def test_reputation_client_agrees_with_the_telecom_list():
    reported = {telecom.syndicate_number(s, k, v)[0] for s in range(2) for k in range(10) for v in (False, True)
                if telecom.syndicate_number(s, k, v)[1]}
    rc = ReputationClient(Telecom(reported))
    probes = list(reported)[:5] + [telecom.genuine_number(k, False)[0] for k in range(5)]
    assert [rc.is_reported(n) for n in probes] == [n in reported for n in probes]
    assert rc.telecom.queries == len(set(probes))  # one round trip per distinct number, then cached


def test_syndicate_numbers_are_partly_reported_genuine_rarely():
    synd = [telecom.syndicate_number(s, k, False)[1] for s in range(12) for k in range(telecom.NUMBERS_PER_SYNDICATE)]
    gen = [telecom.genuine_number(k, False)[1] for k in range(20000)]
    assert 0.35 < np.mean(synd) < 0.55 and np.mean(gen) < 0.01


def test_context_sets_caller_reported_only_through_the_lookup():
    seen = []
    ctx = ContextTracker(lookup=lambda n: seen.append(n) or n.endswith("1"))
    row = ctx.snapshot({"event": "CALL_START", "ts": 0, "caller_kind": "unknown", "caller_number": "+91 7000000001"})
    assert row["caller_reported"] is True and row["caller_number"] == "+91 7000000001" and seen == ["+91 7000000001"]
    assert ctx.snapshot({"event": "BIO_WINDOW", "ts": 5})["caller_reported"] is True        # carried while the call lasts
    assert ctx.snapshot({"event": "CALL_END", "ts": 9})["caller_reported"] is True          # end row still shows the call
    assert ctx.snapshot({"event": "UPI_APP_OPEN", "ts": 10})["caller_reported"] is None
    no_consent = ContextTracker(lookup=lambda n: None)                                      # gate closed -> unknown
    assert no_consent.snapshot({"event": "CALL_START", "ts": 0, "caller_number": "+91 7000000001"})["caller_reported"] is None


# ---------------------------------------------------------------- adaptive scammers
@pytest.fixture(scope="module")
def worlds():
    base = generate(600, 0.3, 5)
    return {k: generate(600, 0.3, 5, adversary={k: True}) for k in ("no_call", "split_amounts", "clean_device", "fresh_numbers")} | {"base": base}


def _scam_events(w):
    ev, se, *_ = w
    return ev[ev["session_id"].isin(se.loc[se["is_scam"], "session_id"])]


def test_adversary_knobs_change_only_scam_sessions(worlds):
    ev0, se0, *_ = worlds["base"]
    for k, (ev, se, *_) in worlds.items():
        if k == "base":
            continue
        benign = lambda e, s: e[e["session_id"].isin(s.loc[~s["is_scam"], "session_id"])].reset_index(drop=True)  # noqa: E731
        assert benign(ev, se)[["event", "ts", "amount"]].equals(benign(ev0, se0)[["event", "ts", "amount"]])


def test_each_knob_does_what_it_says(worlds):
    s = {k: _scam_events(w) for k, w in worlds.items()}
    assert not (s["no_call"]["event"] == "CALL_START").any() and (s["base"]["event"] == "CALL_START").any()
    pays = lambda e: (e["event"] == "PAYMENT_ATTEMPT").sum()  # noqa: E731
    assert pays(s["split_amounts"]) > 2 * pays(s["base"])
    assert not (s["clean_device"]["app_source"] == "sideload").any() and not s["clean_device"]["accessibility_granted"].fillna(False).any()
    calls = s["fresh_numbers"][s["fresh_numbers"]["event"] == "CALL_START"]
    assert len(calls) and not calls["caller_reported"].fillna(False).any()
    base_calls = s["base"][(s["base"]["event"] == "CALL_START") & (s["base"]["caller_kind"] != "contact")]
    assert base_calls["caller_reported"].mean() > 0.2
    assert set(worlds["base"][1].loc[worlds["base"][1]["is_scam"], "typology"]) <= set(SCAM_TYPOLOGIES)
