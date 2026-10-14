"""Backend: payee-side campaign service and its API (no GPU, no trained session models needed)."""
import pandas as pd
import pytest

from backend.campaign_service import CampaignService, campaign_override, to_seconds
from ml.campaign.pipeline import build


@pytest.fixture(scope="module")
def model_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("campaign_model")
    b = build(2000, seed=3, tick_hours=None, verbose=False)
    b.model.meta.update({"flag_threshold": 0.9, "watch_threshold": 0.45})
    b.model.save(d)
    return d


@pytest.fixture(scope="module")
def client(model_dir, tmp_path_factory):
    from fastapi.testclient import TestClient
    mp = pytest.MonkeyPatch()
    mp.setenv("RAKSHAM_SERVICES", "campaign")
    mp.setenv("RAKSHAM_CAMPAIGN_DIR", str(model_dir))
    mp.setenv("RAKSHAM_DEVICE", "cpu")
    from backend import campaign_service
    mp.setattr(campaign_service, "DEMO_DIR", tmp_path_factory.mktemp("demo"))
    from backend.app import app
    with TestClient(app) as c:
        yield c
    mp.undo()


def test_health_lists_only_campaign(client):
    h = client.get("/health").json()
    assert h["loaded"] == ["campaign"] and not h["errors"]


def test_unknown_payee_query_is_read_only(client):
    r = client.post("/v1/payee/score", json={"payee_id": "NEW_ACC", "amount": 40000, "payer_id": "u1", "payee_age_days": 3}).json()
    assert 0 <= r["risk"] <= 1 and r["known_account"] is False and r["band"] in ("ok", "watch", "flag") and r["latency_ms"] < 500
    assert client.get("/v1/campaign/cases").json()["summary"]["accounts_tracked"] == 0  # the query created no state


def test_ingest_builds_state_and_flags_a_fast_pass_through_account(client):
    client.post("/v1/admin/reset")
    t0 = 10 * 86400.0
    last = None
    for i in range(12):  # twelve strangers pay a 5-day-old account, which forwards each payment within minutes
        last = client.post("/v1/campaign/ingest", json={"ts": t0 + i * 600, "src": f"victim{i}", "dst": "MULE1", "amount": 48000,
                                                       "dst_age_days": 5}).json()
        client.post("/v1/campaign/ingest", json={"ts": t0 + i * 600 + 240, "src": "MULE1", "dst": "L2_1", "amount": 47000,
                                                 "src_is_account": True, "dst_age_days": 4})
    q = client.post("/v1/payee/score", json={"payee_id": "MULE1", "amount": 50000, "payer_id": "victim99", "ts": t0 + 8000}).json()
    assert q["known_account"] and q["risk"] > 0.5 and q["reasons"]
    assert last["payee_id"] == "MULE1"
    assert client.get("/v1/campaign/cases").json()["summary"]["accounts_tracked"] >= 3


def test_demo_cases_are_ranked_and_actionable(client):
    client.post("/v1/admin/reset")
    r = client.post("/v1/campaign/demo/load", json={"until_day": 60, "n_sessions": 500, "ambient_scale": 0.1})
    assert r.status_code == 200 and r.json()["replayed_transfers"] > 1000
    body = client.get("/v1/campaign/cases?top=5").json()
    cases = body["cases"]
    assert body["summary"]["flagged"] >= len(cases)
    assert [c["priority"] for c in cases] == sorted((c["priority"] for c in cases), reverse=True)
    for c in cases:
        assert c["summary"]["en"] and c["summary"]["hi"] and c["summary"]["actions"]
        assert any(a["action"] == "credit_hold" and a["needs_human"] for a in c["summary"]["actions"])


def test_hold_is_a_logged_human_action_and_reaches_the_payer_side(client):
    cases = client.get("/v1/campaign/cases?top=3").json()["cases"]
    if not cases:
        pytest.skip("no case opened in this small synthetic window")
    cid, acct = cases[0]["case_id"], cases[0]["accounts"][0]
    assert client.post(f"/v1/campaign/cases/{cid}/hold", json={"analyst": ""}).status_code == 422  # a named analyst is required
    h = client.post(f"/v1/campaign/cases/{cid}/hold", json={"analyst": "priya", "reason": "digital-arrest ring"}).json()
    assert h["held_accounts"] >= 1 and h["analyst"] == "priya"
    assert client.post("/v1/payee/score", json={"payee_id": acct, "amount": 1000}).json()["held"] is True
    assert client.post("/v1/campaign/release", json=[acct]).json()["released"] == 1
    assert client.post("/v1/campaign/cases/CMP-9999/hold", json={"analyst": "priya"}).status_code == 404


def test_campaign_override_never_acts_on_a_weak_single_signal():
    flagged_only = {"case_id": None, "held": False, "band": "flag"}
    assert campaign_override("allow", 0.5, flagged_only) == ("allow", None)               # flagged alone: no change
    in_case = {"case_id": "CMP-1", "held": False}
    assert campaign_override("allow", 0.001, in_case) == ("allow", None)                  # case + calm session: no change
    assert campaign_override("monitor", 0.05, in_case)[0] == "nudge"                      # case + risky session: nudge
    assert campaign_override("hold", 0.9, in_case) == ("hold", None)                      # never lowers an action
    assert campaign_override("allow", 0.0, {"case_id": None, "held": True})[0] == "cool_off"
    assert campaign_override("allow", 0.9, None) == ("allow", None)


def test_to_seconds_accepts_numbers_and_timestamps():
    assert to_seconds(5) == 5.0
    assert to_seconds("2026-01-02T00:00:00") == 86400.0
    assert to_seconds(pd.Timestamp("2026-01-01 00:01:00")) == 60.0


def test_service_loads_without_the_api(model_dir):
    svc = CampaignService(model_dir)
    assert svc.flag == 0.9 and svc.summary()["accounts_tracked"] == 0


def test_session_pipeline_fills_the_payee_slot_from_the_campaign_service(model_dir):
    """The wiring only: the GRU/fusion path needs trained session models and is covered by tests/test_serve.py."""
    from backend.session_service import SessionService
    svc = object.__new__(SessionService)
    svc.campaign = CampaignService(model_dir)
    s = {"start_time": pd.Timestamp("2026-03-01"), "user": {"user_id": "u1"}}
    row = {"event": "PAYMENT_ATTEMPT", "payee_id": "X1", "amount": 5000.0, "ts": 120.0, "payee_mule_score": None,
           "payee_vpa_age_days": 3.0, "payee_is_merchant": False}
    info = svc._payee(s, row)
    assert info["source"] == "campaign" and row["payee_mule_score"] == info["risk"] and 0 <= info["risk"] <= 1
    assert svc._payee(s, dict(row, payee_mule_score=0.42)) == {"source": "client", "risk": 0.42}  # a client-supplied score wins
    assert svc._payee(s, {"event": "CALL_START", "payee_id": None}) is None
    svc.campaign = None
    assert svc._payee(s, dict(row, payee_mule_score=None)) is None


def test_case_graph_and_reload_after_reset(client):
    """A reset followed by a fresh load rebuilds the same cases (the reset used to keep the ledger but drop the
    account metadata, so a reload tracked 0 accounts), and every case has a consistent money-flow graph."""
    def load():
        client.post("/v1/admin/reset", params={"services": "campaign"})
        client.post("/v1/campaign/demo/load", json={"until_day": 60, "n_sessions": 500, "ambient_scale": 0.1})
        return client.get("/v1/campaign/cases?top=5").json()

    first, second = load(), load()
    assert second["summary"]["accounts_tracked"] == first["summary"]["accounts_tracked"] > 0
    assert [c["case_id"] for c in second["cases"]] == [c["case_id"] for c in first["cases"]]
    if not second["cases"]:
        pytest.skip("no case opened in this small synthetic window")
    c = second["cases"][0]
    g = client.get(f"/v1/campaign/cases/{c['case_id']}/graph").json()
    ids = {n["id"] for n in g["nodes"]}
    assert {n["id"] for n in g["nodes"] if n["kind"] == "account"} >= set(c["accounts"])
    assert all(e["src"] in ids and e["dst"] in ids and e["amount"] > 0 for e in g["edges"])
    assert all(n["hop"] >= 1 for n in g["nodes"] if n["kind"] == "account")
    assert client.get("/v1/campaign/cases/NOPE/graph").status_code == 404


def test_scoped_reset_keeps_other_services(client):
    before = client.get("/v1/campaign/cases").json()["summary"]["accounts_tracked"]
    assert client.post("/v1/admin/reset", params={"services": "session"}).json()["reset"] == ["session"]
    assert client.get("/v1/campaign/cases").json()["summary"]["accounts_tracked"] == before
