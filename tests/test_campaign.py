"""Payee-side campaign layer: ledger invariants, feature causality, tracker rules, model persistence, radar."""
import numpy as np
import pandas as pd
import pytest

from ml.campaign.campaigns import CampaignTracker
from ml.campaign.features import FEATURES, MODEL_FEATURES, AccountMeta, FeatureEngine, stream_features
from ml.campaign.ledger import DAY, build_ledger
from ml.campaign.payee_model import PayeeRiskModel
from ml.campaign.pipeline import build
from ml.campaign.radar import Radar
from ml.sim.generate import generate


@pytest.fixture(scope="module")
def sim():
    return generate(1500, 0.2, 3)


@pytest.fixture(scope="module")
def ledger(sim):
    return build_ledger(*sim, seed=5)


def test_ledger_is_time_sorted_and_closed(ledger):
    tr, ac = ledger.transfers, ledger.accounts
    assert tr["ts_s"].is_monotonic_increasing and tr["ts_s"].min() >= 0 and tr["ts_s"].max() < 90 * DAY
    assert set(tr["src"]) | set(tr["dst"]) <= set(ac["account"])
    assert ac["account"].is_unique


def test_scam_credits_land_on_mules_and_forwarding_conserves_money(ledger):
    tr, ac = ledger.transfers, ledger.accounts.set_index("account")
    sc = tr[tr["kind"] == "scam_payment"]
    assert len(sc) and ac.loc[sc["dst"], "is_mule"].all()
    mule_ids = ac.index[ac["is_mule"] & ac["kind"].isin(["mule_l1", "mule_l2", "mule_l3"])]
    inflow = tr[tr["dst"].isin(mule_ids)].groupby("dst")["amount"].sum()
    outflow = tr[tr["src"].isin(mule_ids) & tr["kind"].eq("forward")].groupby("src")["amount"].sum()
    j = pd.concat([inflow, outflow], axis=1, keys=["i", "o"]).fillna(0)
    assert (j["o"] <= j["i"] * 1.02 + 500).all(), "a mule forwarded more than it received"


def test_syndicates_are_consistent_with_sessions(sim, ledger):
    """All mules paid within one session belong to the same syndicate (simulator contract)."""
    events, _, _, payees = sim
    syn = payees.set_index("payee_id")["syndicate"]
    pay = events[events["event"] == "PAYMENT_SUCCESS"]
    pay = pay[pay["payee_id"].isin(syn.index[syn >= 0])]
    assert (pay.groupby("session_id")["payee_id"].agg(lambda x: syn[x].nunique()) == 1).all()


def test_novel_campaigns_start_after_training_period(ledger):
    tr = ledger.transfers
    nov = tr[tr["campaign_truth"].fillna("").str.startswith("NOVEL")]
    assert len(nov) and nov["ts_s"].min() >= 78 * DAY - 1


def test_features_are_causal(ledger):
    """Features of the first k credits do not change when everything after them is removed."""
    tr, ac = ledger.transfers.iloc[:30000].reset_index(drop=True), ledger.accounts
    full = stream_features(tr, ac).credit
    k = 12000
    part = stream_features(tr.iloc[:k].reset_index(drop=True), ac).credit
    a, b = full.loc[full.index < k], part
    assert len(a) == len(b)
    np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), equal_nan=True)


def test_feature_engine_dwell_and_reciprocity():
    eng = FeatureEngine({"A": AccountMeta(30.0, False), "B": AccountMeta(500.0, False)})
    eng.on_transfer(0.0, "victim", "A", 1000.0)       # credit
    eng.on_transfer(300.0, "A", "B", 950.0)           # forwarded after 5 minutes
    f = dict(zip(FEATURES, eng.features("A", 400.0)))
    assert f["has_dwell"] == 1.0 and abs(np.expm1(f["log_median_dwell_min"]) - 5.0) < 1e-6
    assert f["out_ratio_1h"] == pytest.approx(0.95)
    q = dict(zip(FEATURES, eng.features("A", 500.0, "B", 950.0)))  # a query *before* the credit is applied
    assert q["cur_new_payer"] == 1.0 and q["cur_log_amt"] == pytest.approx(np.log1p(950.0))
    eng.on_transfer(500.0, "B", "A", 950.0)           # money comes back in a matching amount
    g = dict(zip(FEATURES, eng.features("A", 600.0)))
    assert g["reciprocal_share_24h"] > 0


def test_tracker_case_needs_corroboration():
    scoreable = {a: True for a in ["m1", "m2", "l2", "benign"]} | {f"v{i}": False for i in range(8)}
    t = CampaignTracker(scoreable, watch=0.2, flag=0.6)
    # one isolated high score on a benign account: watchlist only
    t.observe(10.0, "v0", "benign", 500.0, 0.95)
    assert "benign" in t.flagged_ts and t.watchlist() == ["benign"] and not t.cases(100.0)
    # two mules feed the same layer-2 account: one campaign
    for i, (m, v) in enumerate([("m1", "v1"), ("m2", "v2"), ("m1", "v3"), ("m2", "v4")]):
        t.observe(100.0 + i, v, m, 40000.0, 0.9)
    t.observe(200.0, "m1", "l2", 30000.0, 0.1)
    t.observe(210.0, "m2", "l2", 30000.0, 0.1)
    cases = t.cases(300.0)
    assert len(cases) == 1 and set(cases[0].accounts) == {"m1", "m2", "l2"}
    assert cases[0].n_victims == 4 and cases[0].recoverable == pytest.approx(160000.0)  # 2x50k at the mules + 60k at layer 2


def test_tracker_coincidental_shared_victim_does_not_merge_campaigns():
    scoreable = {a: True for a in ["a1", "b1"]} | {f"v{i}": False for i in range(6)}
    t = CampaignTracker(scoreable, watch=0.2, flag=0.6)
    for v in ("v0", "v1", "v2"):
        t.observe(10.0, v, "a1", 1000.0, 0.95)
        t.observe(20.0, v, "b1", 1000.0, 0.95)
    assert t._find("a1") != t._find("b1")


def test_tracker_ranks_by_recoverable_rupees():
    scoreable = {a: True for a in ["big", "small", "l2a", "l2b"]} | {f"v{i}": False for i in range(20)}
    t = CampaignTracker(scoreable, watch=0.2, flag=0.6)
    for i in range(5):
        t.observe(10.0 + i, f"v{i}", "big", 100000.0, 0.95)
        t.observe(10.0 + i, f"v{i + 5}", "small", 1000.0, 0.95)
    t.observe(50.0, "big", "l2a", 1000.0, None)
    t.observe(50.0, "small", "l2b", 100.0, None)
    cases = t.cases(100.0)
    assert [c.accounts[0] for c in cases][0] in ("big", "l2a") and cases[0].recoverable > cases[-1].recoverable


@pytest.fixture(scope="module")
def bundle():
    return build(2500, seed=3, tick_hours=None, verbose=False)


def test_scores_are_honest_and_ordered(bundle):
    c = bundle.credit
    assert c["risk"].between(0, 1).all()
    te = c[c["day"] >= bundle.split_days[1]]
    assert te.loc[te["y"] == 1, "risk"].mean() > te.loc[te["y"] == 0, "risk"].mean() + 0.3


def test_model_roundtrip(bundle, tmp_path):
    bundle.model.save(tmp_path)
    m2 = PayeeRiskModel.load(tmp_path)
    X = bundle.credit[FEATURES].iloc[:200]
    np.testing.assert_allclose(bundle.model.predict(X), m2.predict(X), atol=1e-9)
    assert list(m2.meta) and set(MODEL_FEATURES) <= set(FEATURES)


def test_reasons_are_on_the_risky_side(bundle):
    c = bundle.credit
    row = c.loc[c["risk"].idxmax(), FEATURES]
    why = bundle.model.reasons(row, k=3)
    assert 1 <= len(why) <= 3 and all(isinstance(t, str) for t, _ in why)


def test_radar_flags_a_planted_cluster():
    rng = np.random.default_rng(0)
    from ml.campaign.features import RADAR_FEATURES
    ref = pd.DataFrame(rng.normal(0, 1, (3000, len(RADAR_FEATURES))), columns=RADAR_FEATURES)
    radar = Radar(quantile=0.99, min_cluster=4, min_ticks=1).fit(ref)
    snap = pd.DataFrame(rng.normal(0, 1, (60, len(RADAR_FEATURES))), columns=RADAR_FEATURES)
    snap.iloc[:8] = rng.normal(6, 0.2, (8, len(RADAR_FEATURES)))
    snap.insert(0, "account", [f"x{i}" for i in range(60)])
    snap.insert(0, "ts_s", 3600.0)
    found = radar.scan(snap, np.zeros(60), flag=0.5, start_ts=0.0)
    assert found and {f"x{i}" for i in range(8)} <= set().union(*(e.accounts for e in found))
