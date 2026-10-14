import numpy as np
import pandas as pd
import pytest

from ml.engine.fusion import FusionModel
from ml.engine.messages import render
from ml.engine.policy import AlertPolicy

T0 = pd.Timestamp("2026-03-01")


def _row(session="S1", user="U1", amount=20000.0, trusted=0.0, typ="digital_arrest", conf=0.9):
    return pd.Series({"session_id": session, "user_id": user, "amount": amount, "payee_known_trusted": trusted,
                      "pred_typology": typ, f"typ_{typ}": conf})


def test_ev_choice_escalates_with_risk_and_amount():
    pol = AlertPolicy()
    ranks = [pol.ev_choice(p, 20000).rank for p in (1e-5, 0.01, 0.05, 0.5)]
    assert ranks == sorted(ranks) and ranks[0] == 0 and ranks[-1] == 3
    assert pol.ev_choice(0.05, 50).rank <= pol.ev_choice(0.05, 50000).rank


def test_session_hold_persists_without_new_notification():
    pol = AlertPolicy()
    d1 = pol.decide(_row(), 0.9, T0)
    d2 = pol.decide(_row(amount=100.0), 1e-6, T0)
    assert (d1.action, d1.notify) == ("hold", True)
    assert (d2.action, d2.notify, d2.suppressed_by) == ("hold", False, "session_on_hold")


def test_escalates_when_user_proceeds_after_warning():
    pol = AlertPolicy()
    p = next(p for p in np.linspace(1e-4, 0.5, 2000) if pol.ev_choice(p, 20000).name == "nudge")
    assert pol.decide(_row(), p, T0).action == "nudge"
    d = pol.decide(_row(), p, T0)
    assert d.action == "cool_off" and d.suppressed_by == "escalated_on_repeat" and d.notify


def test_trusted_payee_and_user_budget():
    pol = AlertPolicy(user_budget=2)
    p = next(p for p in np.linspace(1e-4, 0.5, 2000) if pol.ev_choice(p, 20000).name == "nudge")
    assert pol.decide(_row(trusted=1.0), p, T0).suppressed_by == "trusted_payee"
    for k in range(2):
        assert pol.decide(_row(session=f"A{k}"), p, T0 + pd.Timedelta(days=k)).action == "nudge"
    d = pol.decide(_row(session="A2"), p, T0 + pd.Timedelta(days=3))
    assert d.suppressed_by == "user_budget" and not d.notify
    assert pol.decide(_row(session="A3"), p, T0 + pd.Timedelta(days=40)).action == "nudge"  # window expired
    assert pol.decide(_row(session="A4"), 0.9, T0 + pd.Timedelta(days=40)).action == "hold"  # hold never budgeted


def test_no_anti_fatigue_repeats_same_tier():
    pol = AlertPolicy(anti_fatigue=False)
    p = next(p for p in np.linspace(1e-4, 0.5, 2000) if pol.ev_choice(p, 20000).name == "nudge")
    assert [pol.decide(_row(), p, T0).action for _ in range(3)] == ["nudge"] * 3


def _fusion_data(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.random(n) < 0.3
    t = pd.DataFrame({
        "gru_p": np.clip(np.where(y, rng.beta(5, 2, n), rng.beta(1, 8, n)), 1e-4, 1 - 1e-4),
        "mule_score": np.where(y, rng.beta(3, 3, n), rng.beta(1, 8, n)),
        "bio_dev": rng.random(n), "log_amt_vs_avg": rng.normal(1, 1, n), "payee_is_new": (rng.random(n) < 0.5) * 1.0,
        "unknown_call_active": (rng.random(n) < 0.2) * 1.0, "payee_known_trusted": (rng.random(n) < 0.3) * 1.0,
        "caller_reported_active": np.where(y, rng.random(n) < 0.4, rng.random(n) < 0.01) * 1.0,
        "is_scam": y, "in_progress": y.astype(int)})
    return t


def test_fusion_is_monotone_and_prior_shift_lowers_risk():
    t = _fusion_data()
    f = FusionModel(real_prior=0.3).fit(t)
    probe = pd.concat([t.iloc[[0]]] * 11, ignore_index=True).assign(mule_score=np.linspace(0, 1, 11))
    p = f.proba(probe)
    assert np.all(np.diff(p) >= -1e-9)
    hi = f.proba(t.iloc[:50])
    lo = f.set_prior(0.005).proba(t.iloc[:50])
    assert np.all(lo < hi)


def test_reasons_never_contradict_data():
    t = _fusion_data()
    f = FusionModel().fit(t)
    low_mule = t.assign(mule_score=0.0, gru_p=0.99).iloc[[0]]
    assert all("mule" not in r for r, _ in f.reasons(low_mule, k=6))


def test_messages_bilingual_with_fallback():
    en, hi = render("hold", "digital_arrest", [])
    assert "1930" in en and "1930" in hi and en.startswith("This payment is on hold")
    en, hi = render("nudge", None, ["first payment to this account"])
    assert "first payment to this account" in en and hi


def test_outcomes_count_one_hold_per_session():
    """A payment that stays held in an already-held session is the same hold: it must not add another
    independent 90% chance of stopping the scam, nor count as a new hold."""
    from ml.engine.simulate import outcomes
    rows = [dict(session_id="S", user_id="U", ts=float(t), amount=1000.0, is_scam=True, extraction_ts=0.0, in_progress=1,
                 typology="digital_arrest", action="hold", notify=(t == 0)) for t in range(5)]
    rows.append(dict(session_id="B", user_id="V", ts=0.0, amount=500.0, is_scam=False, extraction_ts=float("nan"),
                     in_progress=0, typology="routine", action="hold", notify=True))
    rows.append(dict(session_id="B", user_id="V", ts=1.0, amount=500.0, is_scam=False, extraction_ts=float("nan"),
                     in_progress=0, typology="routine", action="hold", notify=False))
    o = outcomes(pd.DataFrame(rows))
    assert o["scams_expected_stopped_in_time_pct"] == pytest.approx(90.0)
    assert o["expected_money_saved_pct"] == pytest.approx(90.0)
    assert o["benign_holds_per_1k_sessions"] == pytest.approx(1000.0)  # one new hold in one benign session


def test_no_anti_fatigue_does_not_keep_session_hold():
    pol = AlertPolicy(anti_fatigue=False)
    assert pol.decide(_row(), 0.9, T0).action == "hold"
    d = pol.decide(_row(), 0.9, T0)
    assert d.suppressed_by is None and d.notify  # without anti-fatigue a repeat hold is a new interruption
