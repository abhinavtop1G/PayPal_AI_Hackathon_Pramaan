"""API tests against the real models (skipped when artifacts/datasets or CUDA are unavailable)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
NEEDED = ["ml/campaign/artifacts/payee_risk_xgb.json", "ml/models/workflow/artifacts/workflow_gru.pt", "ml/engine/artifacts/fusion_xgb.json", "ml/models/gnn/artifacts/aml_diff.pt",
          "DATA/aml/hi_small_edges.npz", "ml/models/biometrics/artifacts/hmog_bilstm.pt", "DATA/hmog/gestures.parquet",
          "ml/models/tabular/artifacts/xgb_ieee.ubj"]
pytestmark = pytest.mark.skipif(not torch.cuda.is_available() or not all(Path(p).exists() for p in NEEDED),
                                reason="needs CUDA, trained artifacts and local datasets")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.app import app
    with TestClient(app) as c:
        yield c


def test_health_all_services(client):
    h = client.get("/health").json()
    assert h["loaded"] == ["biometrics", "campaign", "gnn", "session", "tabular"] and not h["errors"]


def test_demo_digital_arrest_held_at_extraction(client):
    b = client.post("/v1/demo/digital_arrest").json()
    first = next(e for e in b["timeline"] if e["decision"])
    assert first["ts_min"] <= b["extraction_ts_min"] + 1e-6
    assert first["decision"]["action"] == "hold" and first["decision"]["notify"]
    assert "1930" in first["decision"]["message_en"] and "1930" in first["decision"]["message_hi"]
    assert first["workflow"]["stage"] == "extraction" and "digital_arrest" in first["workflow"]["typology_top3"]


@pytest.mark.parametrize("typ", ["family_transfer", "genuine_urgent_family", "hospital_emergency"])
def test_demo_benign_not_interrupted(client, typ):
    b = client.post(f"/v1/demo/{typ}").json()
    assert not any(e["decision"]["notify"] for e in b["timeline"] if e["decision"])


def test_session_validation(client):
    user = {"user_id": "u1", "avg_txn_amount": 900}
    assert client.post("/v1/session/s-val/start", json={"user": user, "start_time": "2026-03-01T10:00:00"}).status_code == 200
    assert client.post("/v1/session/s-val/events", json={"event": "CALL_START", "ts": 10, "caller_kind": "unknown"}).status_code == 200
    assert client.post("/v1/session/s-val/events", json={"event": "CALL_END", "ts": 5}).status_code == 422       # out of order
    assert client.post("/v1/session/s-val/events", json={"event": "TELEPORT", "ts": 20}).status_code == 422       # unknown type
    assert client.post("/v1/session/missing/events", json={"event": "CALL_END", "ts": 1}).status_code == 404


def test_session_matches_offline_pipeline(client):
    """Raw events streamed through the API reproduce the offline GRU scores (server rebuilds context, checks the caller's
    number with the telecom and scores the touch gestures with the real model, exactly as offline training data was built)."""
    from ml.engine.components import gru_outputs, load_gru
    from ml.models.workflow.data import SIM_DIR, load
    ev = pd.read_parquet(SIM_DIR / "events.parquet")
    users = pd.read_parquet(SIM_DIR / "users.parquet").set_index("user_id")
    d = load()["test"]
    offline = gru_outputs(load_gru(), d)
    from ml.sim.hmog_bank import HmogBank
    bank = HmogBank.load()
    raw_cols = ["event", "ts", "caller_kind", "call_video", "caller_number", "sms_sender_kind", "sms_has_link", "app_source", "payee_id",
                "payee_is_merchant", "payee_is_new", "payee_vpa_age_days", "payee_mule_score", "amount", "bio_pressure",
                "bio_swipe_velocity", "bio_tap_interval_ms", "bio_hesitation_ms", "bio_orientation_var"]
    for i in np.random.default_rng(1).choice(len(d.num), 8, replace=False):
        sid, uid = d.sessions["session_id"].iloc[i], d.sessions["user_id"].iloc[i]
        prof = {k: float(v) for k, v in users.loc[uid].items() if k.startswith("bio_") or k == "avg_txn_amount"}
        prof["hmog_subject"] = int(users.loc[uid, "hmog_subject"])
        client.post(f"/v1/session/p-{sid}/start", json={"user": {"user_id": uid, **prof},
                                                         "start_time": d.sessions["start_time"].iloc[i].isoformat()})
        for k, (_, r) in enumerate(ev[ev["session_id"] == sid].iterrows()):
            body = {c: (r[c].item() if hasattr(r[c], "item") else r[c]) for c in raw_cols if not pd.isna(r[c])}
            if r["event"] != "CALL_START":
                body.pop("caller_kind", None), body.pop("call_video", None), body.pop("caller_number", None)
            if isinstance(r["bio_ref"], str):
                body["gestures"] = bank.resolve(r["bio_ref"])[1]
            out = client.post(f"/v1/session/p-{sid}/events", json=body).json()
            assert abs(out["workflow"]["p_scam_in_progress"] - offline[i][0][k]) < 1e-4


def _transfer(**kw):
    t = {"timestamp": "2022-09-12T10:00:00", "from_bank": "070", "from_account": "100428660", "to_bank": "001",
         "to_account": "8000EBD30", "amount_paid": 5000, "amount_received": 5000, "payment_currency": "US Dollar",
         "receiving_currency": "US Dollar", "payment_format": "ACH", "record": False}
    t.update(kw)
    return t


def test_gnn_score_and_online_history(client):
    from ml.models.gnn.data import load_aml, load_vocab
    g, v = load_aml(), load_vocab()
    busy = v["accounts"][np.bincount(g.src).argmax()]
    fb, fa = busy.split("_", 1)
    r1 = client.post("/v1/gnn/score", json=_transfer(from_bank=fb, from_account=fa, record=True)).json()
    assert 0 <= r1["p_laundering"] <= 1 and len(r1["explanation"]["sender"]["top_attended"]) == 3
    r2 = client.post("/v1/gnn/score", json=_transfer(from_bank=fb, from_account=fa)).json()
    assert r2["explanation"]["sender"]["history_total"] == r1["explanation"]["sender"]["history_total"] + 1
    new = client.post("/v1/gnn/score", json=_transfer(from_bank="999", from_account="NEW1", to_bank="999", to_account="NEW2")).json()
    assert new["explanation"]["sender"]["history_total"] == 0
    assert client.post("/v1/gnn/score", json=_transfer(payment_currency="Doubloon")).status_code == 422


def test_biometrics_enroll_verify(client):
    from ml.models.biometrics.data import FEATURES, load_gestures
    df = load_gestures()
    u = df[df["user"] == df["user"].iloc[0]]
    recs = lambda x: x[FEATURES].astype(float).where(x[FEATURES].notna(), None).to_dict("records")  # noqa: E731
    assert client.post("/v1/biometrics/enroll", json={"user_id": "hmog", "gestures": recs(u.iloc[:200])}).json()["enrolled"]
    r = client.post("/v1/biometrics/verify", json={"user_id": "hmog", "gestures": recs(u.iloc[300:320])}).json()
    assert r["window_gestures"] == 20 and -1 <= r["similarity_lstm"] <= 1 and isinstance(r["matches_profile"], bool)
    assert client.post("/v1/biometrics/verify", json={"user_id": "hmog", "gestures": recs(u.iloc[:5])}).status_code == 422
    assert client.post("/v1/biometrics/verify", json={"user_id": "nobody", "gestures": recs(u.iloc[:20])}).status_code == 404


def test_tabular_score(client):
    r = client.post("/v1/tabular/score", json={"transactions": [{"TransactionAmt": 120.0, "ProductCD": "W", "card4": "visa"}, {}]})
    assert r.status_code == 200 and len(r.json()["p_fraud"]) == 2
    assert client.post("/v1/tabular/score", json={"transactions": [{"not_a_feature": 1}]}).status_code == 422


def test_caller_reputation_respects_consent(client):
    nums = client.get("/v1/demo/numbers").json()
    user = {"user_id": "u-consent", "avg_txn_amount": 900}
    call = {"event": "CALL_START", "ts": 1, "caller_kind": "unknown", "caller_number": nums["reported"][0]}
    client.post("/v1/session/c-yes/start", json={"user": user, "start_time": "2026-03-01T10:00:00"})
    assert client.post("/v1/session/c-yes/events", json=call).json()["signals"]["caller_reported"] is True
    client.post("/v1/session/c-no/start", json={"user": user, "start_time": "2026-03-01T10:00:00", "consent": ["fraud_prevention"]})
    assert client.post("/v1/session/c-no/events", json=call).json()["signals"]["caller_reported"] is None  # gate closed
    clean = dict(call, caller_number=nums["clean"][0])
    client.post("/v1/session/c-clean/start", json={"user": user, "start_time": "2026-03-01T10:00:00"})
    assert client.post("/v1/session/c-clean/events", json=clean).json()["signals"]["caller_reported"] is False
    assert client.post("/v1/consent/check", json={"principal": "u-consent", "purpose": "marketing"}).json()["allowed"] is False


def test_touch_window_scored_by_the_real_model(client):
    own, other = client.get("/v1/demo/touch?profile=normal").json(), client.get("/v1/demo/touch?profile=remote").json()
    user = {"user_id": "u-touch", "avg_txn_amount": 900, "hmog_subject": own["subject"]}
    assert client.post("/v1/session/t1/start", json={"user": user, "start_time": "2026-03-01T10:00:00"}).json()["touch_profile"]
    sig = lambda g, ts: client.post("/v1/session/t1/events", json={"event": "BIO_WINDOW", "ts": ts, "gestures": g}).json()["signals"]["touch"]  # noqa: E731
    a, b = sig(own["gestures"], 1), sig(other["gestures"], 2)
    assert a is not None and b is not None and b["behavioural_deviation"] > a["behavioural_deviation"] - 1.0


def test_psi_demo_endpoint(client):
    nums = client.get("/v1/demo/numbers").json()
    r = client.post("/v1/telecom/psi/demo", json={"bank_numbers": nums["reported"][:2] + nums["clean"][:2]}).json()
    assert sorted(r["matches"]) == sorted(nums["reported"][:2]) and r["bank_size"] == 4
