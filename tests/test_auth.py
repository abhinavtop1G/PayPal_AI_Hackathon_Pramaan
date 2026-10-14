"""Transaction authentication (BIOS): state, features, policy, engine, security and the API."""
import json
import math
from pathlib import Path

import pytest

from ml.auth.features import FEATURES, build
from ml.auth.geo import ip_kind, parse_geo_header
from ml.auth.policy import AuthPolicy
from ml.auth.sim import SimConfig, attach_bio, generate
from ml.auth.state import DAY, AuthState, MemoryKV

MODEL = Path("ml/auth/artifacts/auth_xgb.json")
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="run python -m ml.auth.evaluate first")
T = 1_780_000_000.0


def _req(uid="u1", ts=T, device="d1", city="Mumbai", lat=19.07, lon=72.87, ip="49.36.1.2", amount=500.0, payee="p1",
         sim_h=None):
    return {"user_id": uid, "ts": ts, "device": {"device_id": device, "sim_change_hours": sim_h},
            "network": {"ip": ip, "city": city, "lat": lat, "lon": lon}, "behaviour": {},
            "transaction": {"amount": amount, "payee_id": payee}}


# ---------------------------------------------------------------------------- geo / IP
def test_ip_kind():
    assert ip_kind("34.93.10.77") == "datacenter"      # Google Cloud range
    assert ip_kind("185.220.101.4") == "anonymiser"    # Tor exit range
    assert ip_kind("49.36.112.45") == "residential"
    assert ip_kind("10.0.0.1") == "unknown" and ip_kind("not-an-ip") == "unknown" and ip_kind(None) == "unknown"


def test_geo_header():
    assert parse_geo_header("mumbai,19.0760,72.8777") == {"city": "Mumbai", "lat": 19.076, "lon": 72.8777}
    assert parse_geo_header("") is None and parse_geo_header("x,y") is None


# ---------------------------------------------------------------------------- state + features
def test_features_are_read_only_and_cover_spec():
    st = AuthState(MemoryKV())
    f, _ = build(_req(), st)
    assert list(f) == FEATURES
    assert st.kv.d == {}  # building features never writes state


def test_device_becomes_known_then_trusted():
    st = AuthState(MemoryKV())
    f, ctx = build(_req(), st)
    assert f["device_new"] == 1 and not ctx["device_trusted"]
    st.commit("u1", _req(), T)
    f, ctx = build(_req(ts=T + 3600), st)
    assert f["device_new"] == 0 and f["device_untrusted"] == 1
    for k in range(1, 4):
        st.commit("u1", _req(ts=T + k * 3 * DAY), T + k * 3 * DAY)
    f, ctx = build(_req(ts=T + 10 * DAY), st)
    assert f["device_untrusted"] == 0 and ctx["device_trusted"]


def test_impossible_travel_and_new_city():
    st = AuthState(MemoryKV())
    for k in range(4):
        st.commit("u1", _req(ts=T + k * DAY), T + k * DAY)
    near, _ = build(_req(ts=T + 3 * DAY + 3600), st)
    far, _ = build(_req(ts=T + 3 * DAY + 600, city="Delhi", lat=28.61, lon=77.21), st)  # ~1,150 km in 10 minutes
    assert far["geo_speed"] > math.log1p(1000) > near["geo_speed"]
    assert far["new_city"] == 1 and near["new_city"] == 0


def test_device_and_ip_fan_out():
    st = AuthState(MemoryKV())
    for i in range(12):
        st.record_attempt(f"v{i}", "bot-1", "34.93.10.77", T + i)
    f, _ = build(_req(uid="u1", device="bot-1", ip="34.93.10.77", ts=T + 60), st)
    assert f["accounts_on_device"] == 12 and f["ip_accounts_1h"] == 12 and f["ip_datacenter"] == 1


def test_amount_vs_history():
    st = AuthState(MemoryKV())
    for k in range(10):
        st.commit("u1", _req(ts=T + k * DAY, amount=500 + 10 * k), T + k * DAY)
    usual, _ = build(_req(ts=T + 11 * DAY, amount=520), st)
    big, _ = build(_req(ts=T + 11 * DAY, amount=50000), st)
    assert big["amt_z"] > 3 > abs(usual["amt_z"])


# ---------------------------------------------------------------------------- policy
def _f(**kw):
    f = {k: 0.0 for k in FEATURES}
    f["bio_dev"] = float("nan")
    f.update(kw)
    return f


def test_challenge_choice():
    pol = AuthPolicy()
    assert pol.choose_challenge(_f(sim_fresh=0.9, device_new=1), {"has_other_trusted_device": True}) == "passkey"
    assert pol.choose_challenge(_f(sim_fresh=0.9, device_new=1), {}) == "passkey"     # never SMS OTP after a SIM change
    assert pol.choose_challenge(_f(remote_access_app=1), {"device_trusted": True}) == "bank_callback"
    assert pol.choose_challenge(_f(unknown_call_active=1, bio_dev=-1.0), {"device_trusted": True}) == "cool_off"
    assert pol.choose_challenge(_f(device_new=1), {"has_other_trusted_device": True}) == "passkey"
    assert pol.choose_challenge(_f(amt_z=4), {"device_trusted": True}) == "sms_otp"


def test_decisions():
    pol = AuthPolicy()
    assert pol.decide(1e-5, 500, _f(), {"device_trusted": True})["decision"] == "allow"
    d = pol.decide(0.2, 80000, _f(amt_z=4), {"device_trusted": True})
    assert d["decision"] == "challenge"                       # risky but not likely: challenge, never block below 50%
    assert pol.decide(0.95, 50000, _f(), {})["decision"] == "block"
    assert pol.decide(1e-5, 500, _f(), {"last_fail_age_s": 60})["decision"] == "block"
    assert pol.decide(1e-6, 100, _f(emulator=1, ip_datacenter=1), {})["decision"] == "challenge"
    assert json.dumps(d)  # JSON-safe (no inf)


# ---------------------------------------------------------------------------- simulator
def test_simulator_is_deterministic_and_labelled():
    a = generate(SimConfig(n_users=60, days=10, attacked_frac=0.2, bot_campaigns=2, seed=3))
    b = generate(SimConfig(n_users=60, days=10, attacked_frac=0.2, bot_campaigns=2, seed=3))
    assert [r["event_id"] for r in a] == [r["event_id"] for r in b] and len(a) > 300
    assert all(a[i]["ts"] <= a[i + 1]["ts"] for i in range(len(a) - 1))
    scen = {r["label"]["scenario"] for r in a if r["label"]["is_attack"]}
    assert "bot" in scen and len(scen) >= 3
    if Path("ml/auth/artifacts/bio_quantiles.json").exists():
        assert attach_bio(a) == "quantiles"
        assert all("bio_dev" in r["behaviour"] for r in a if r.get("bio_profile"))


# ---------------------------------------------------------------------------- engine
@needs_model
def test_engine_challenge_flow():
    from ml.auth.engine import AuthEngine
    from ml.auth.model import AuthModel
    eng = AuthEngine(AuthModel.load(), state=AuthState(MemoryKV()))
    for k in range(30):
        eng.state.commit("u1", _req(ts=T + k * DAY / 2, amount=600), T + k * DAY / 2)
    now = T + 15.5 * DAY
    ok = eng.authenticate(_req(ts=now, amount=600))
    assert ok["decision"] == "allow" and ok["reasons"] == []
    atk = eng.authenticate(_req(ts=now + 300, device="atk", city="Kolkata", lat=22.57, lon=88.36, ip="34.93.1.1",
                                amount=60000, payee="mule", sim_h=2.0))
    assert atk["decision"] in ("challenge", "block") and atk["reasons"]
    assert sum(s["contribution"] for s in atk["signals"]) == pytest.approx(sum(atk["family_contribution"].values()), abs=1e-3)
    if atk["decision"] == "challenge":
        assert atk["challenge_type"] != "sms_otp"
        assert eng.verify_challenge(atk["decision_id"], False)["decision"] == "block"
        again = eng.authenticate(_req(ts=now + 400, amount=600))
        assert again["decision"] == "block" and again["rule"] == "recent_failed_challenge"
    with pytest.raises(KeyError):
        eng.verify_challenge("nope", True)


@needs_model
def test_passed_passkey_trusts_device():
    from ml.auth.engine import AuthEngine
    from ml.auth.model import AuthModel
    eng = AuthEngine(AuthModel.load(), state=AuthState(MemoryKV()))
    eng.state.put_pending("x1", {"req": _req(device="new-phone"), "challenge_type": "passkey", "p": 0.1})
    out = eng.verify_challenge("x1", True)
    assert out["decision"] == "allow" and out["device_trusted"]
    _, ctx = build(_req(device="new-phone", ts=T + 60), eng.state)
    assert ctx["device_trusted"]


# ---------------------------------------------------------------------------- security middleware
def _secured_app(monkeypatch, **env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.security import SecurityMiddleware
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.post("/v1/echo")
    def echo(body: dict):
        return body

    @app.get("/health")
    def health():
        return {"ok": True}
    return TestClient(app)


def test_api_key_and_hmac(monkeypatch):
    from backend.security import sign
    c = _secured_app(monkeypatch, BIOS_API_KEYS="k1,k2", BIOS_HMAC_SECRET="s3cret", BIOS_RATE_LIMIT="1000")
    body = json.dumps({"a": 1}).encode()
    assert c.get("/health").status_code == 200                                 # exempt
    assert c.post("/v1/echo", content=body).status_code == 401                 # no key
    assert c.post("/v1/echo", content=body, headers={"X-API-Key": "k2"}).status_code == 401  # no signature
    h = {"X-API-Key": "k2", "Content-Type": "application/json", **sign("s3cret", body)}
    r = c.post("/v1/echo", content=body, headers=h)
    assert r.status_code == 200 and r.json() == {"a": 1}                       # body replayed to the endpoint
    assert c.post("/v1/echo", content=body, headers=h).status_code == 409      # replay
    bad = {**h, **sign("wrong", body)}
    assert c.post("/v1/echo", content=body, headers=bad).status_code == 401
    old = {"X-API-Key": "k1", "Content-Type": "application/json", **sign("s3cret", body, ts=1)}
    assert c.post("/v1/echo", content=body, headers=old).status_code == 401    # outside the 5-minute window


def test_rate_limit(monkeypatch):
    c = _secured_app(monkeypatch, BIOS_RATE_LIMIT="2")
    codes = [c.post("/v1/echo", json={}).status_code for _ in range(10)]
    assert codes[0] == 200 and 429 in codes


# ---------------------------------------------------------------------------- API
@pytest.fixture(scope="module")
def client():
    import os
    from fastapi.testclient import TestClient
    os.environ["BIOS_SERVICES"] = "auth"
    os.environ["BIOS_AUDIT_DB"] = "checkpoints/test_audit.sqlite"
    from backend.app import app
    with TestClient(app) as c:
        yield c
    os.environ.pop("BIOS_SERVICES", None)


@needs_model
def test_api_authenticate_and_verify(client):
    h = client.get("/health").json()
    assert "auth" in h["loaded"] and h["auth"]["features"] == len(FEATURES)
    body = {"user_id": "api-user", "device": {"device_id": "phone-1", "platform": "android"},
            "network": {"ip": "49.36.1.9"}, "transaction": {"amount": 750, "payee_id": "shop"}}
    r = client.post("/v1/authenticate", json=body, headers={"X-Client-Geo-Location": "pune,18.52,73.85"})
    assert r.status_code == 200
    out = r.json()
    assert out["decision"] in ("allow", "challenge", "block") and 0 <= out["risk_score"] <= 1
    assert out["features"]["geo_speed"] is None  # first sighting: no previous location
    assert client.post("/v1/authenticate", json={"user_id": "x"}).status_code == 422  # device is required
    assert client.post("/v1/challenge/verify", json={"decision_id": "missing", "passed": True}).status_code == 404


@needs_model
@pytest.mark.parametrize("scenario", ["genuine_routine", "genuine_travel"])
def test_demo_genuine_allowed(client, scenario):
    r = client.post(f"/v1/auth/demo/{scenario}").json()
    assert r["response"]["decision"] == "allow", r["response"]


@needs_model
@pytest.mark.parametrize("scenario", ["ato_new_device", "sim_swap", "bot", "remote_access", "coerced"])
def test_demo_attacks_not_allowed(client, scenario):
    r = client.post(f"/v1/auth/demo/{scenario}").json()["response"]
    assert r["decision"] in ("challenge", "block") and r["reasons"], r
    if r["decision"] == "challenge":
        assert r["challenge_type"] != "sms_otp" or scenario == "bot"


@needs_model
def test_feed_and_stats(client):
    client.post("/v1/auth/demo/genuine_routine")
    assert client.get("/v1/auth/decisions?limit=5").json()
    s = client.get("/v1/auth/stats").json()
    assert s["decisions"] >= 1 and "allow" in s["by_decision"]


def test_new_device_binding():
    pol = AuthPolicy()
    d = pol.decide(1e-5, 1500, _f(device_new=1, sim_fresh=0.97), {"has_other_trusted_device": True})
    assert d["decision"] == "challenge" and d["rule"] == "new_device_binding" and d["challenge_type"] == "passkey"
    assert pol.decide(1e-5, 0, _f(device_new=1), {})["decision"] == "allow"   # a login is not a payment
