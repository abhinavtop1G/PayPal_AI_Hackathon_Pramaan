"""The session builder's touch demo must work from a clean checkout, on a CPU, without the HMOG dataset.

tests/test_serve.py covers the same flow but skips itself without a GPU and the datasets, which hid a 503 from
/v1/demo/touch on every other machine.
"""
import os

import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from backend.app import REGISTRY, app
    saved = {k: os.environ.get(k) for k in ("PRAMAAN_SERVICES", "RAKSHAM_DEVICE", "BIO_CALIB")}
    os.environ.update(PRAMAAN_SERVICES="session", RAKSHAM_DEVICE="cpu", BIO_CALIB="ml/auth/artifacts/bio_calib.pkl")
    REGISTRY["errors"].clear()
    with TestClient(app) as c:
        yield c
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_demo_touch_returns_real_gestures(client):
    for profile in ("normal", "coerced", "remote"):
        r = client.get(f"/v1/demo/touch?profile={profile}")
        assert r.status_code == 200, r.text
        assert len(r.json()["gestures"]) >= 10


def test_demo_touch_rejects_an_unknown_profile(client):
    assert client.get("/v1/demo/touch?profile=nope").status_code == 422


def test_builder_session_scores_touch(client):
    own, other = client.get("/v1/demo/touch?profile=normal").json(), client.get("/v1/demo/touch?profile=remote").json()
    user = {"user_id": "u-builder", "avg_txn_amount": 900, "hmog_subject": own["subject"]}
    started = client.post("/v1/session/b1/start", json={"user": user, "start_time": "2026-03-01T10:00:00"})
    assert started.status_code == 200, started.text
    assert started.json()["touch_profile"]

    def touch(gestures, ts):
        r = client.post("/v1/session/b1/events", json={"event": "BIO_WINDOW", "ts": ts, "gestures": gestures})
        assert r.status_code == 200, r.text
        return r.json()["signals"]["touch"]

    mine, theirs = touch(own["gestures"], 1), touch(other["gestures"], 2)
    assert mine is not None and theirs is not None
    assert theirs["behavioural_deviation"] > mine["behavioural_deviation"]
