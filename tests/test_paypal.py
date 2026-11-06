"""The PayPal gate: what reaches PayPal, and what must not. PayPal itself is replaced by a local fake of its REST API."""
import base64
import json
import os

import httpx
import pytest

from backend.paypal_service import (GateClosed, NotConfigured, OrderMismatch, PayPalCheckout, PayPalClient, PayPalError,
                                    client_from_env)
from ml.auth.state import MemoryKV


class FakePayPal:
    """Enough of PayPal's sandbox API to test against, recording every request it receives."""

    def __init__(self, expires_in=3600):
        self.requests: list[httpx.Request] = []
        self.orders: dict[str, dict] = {}
        self.expires_in = expires_in
        self.tokens = 0
        self.decline_next = False
        self.revoke_next = False

    def calls(self, path_part: str = "") -> list[httpx.Request]:
        return [r for r in self.requests if path_part in r.url.path]

    def approve(self, order_id: str) -> None:
        self.orders[order_id]["status"] = "APPROVED"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/oauth2/token":
            if base64.b64decode(request.headers["authorization"].split()[1]) != b"cid:secret":
                return httpx.Response(401, json={"error": "invalid_client", "error_description": "bad"})
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"token-{self.tokens}", "token_type": "Bearer", "expires_in": self.expires_in})
        if request.headers.get("authorization") != f"Bearer token-{self.tokens}" or self.revoke_next:
            self.revoke_next = False
            return httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"})
        if path == "/v2/checkout/orders":
            body = json.loads(request.content)
            oid = f"ORDER{len(self.orders) + 1}"
            self.orders[oid] = {"id": oid, "status": "CREATED", "intent": body["intent"], "purchase_units": body["purchase_units"]}
            return httpx.Response(201, json=self.orders[oid])
        if path.endswith("/capture"):
            order = self.orders[path.split("/")[-2]]
            if self.decline_next:
                self.decline_next = False
                return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "debug_id": "dbg1", "message": "declined",
                                                 "details": [{"issue": "INSTRUMENT_DECLINED"}]})
            if order["status"] == "COMPLETED":
                return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]})
            order["status"] = "COMPLETED"
            order["purchase_units"][0]["payments"] = {"captures": [
                {"id": "CAP1", "status": "COMPLETED", "amount": order["purchase_units"][0]["amount"]}]}
            return httpx.Response(201, json=order)
        if "/v2/checkout/orders/" in path:
            return httpx.Response(200, json=self.orders[path.split("/")[-1]])
        if path.endswith("/refund"):
            return httpx.Response(201, json={"id": "REF1", "status": "COMPLETED"})
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})


class FakeDemo:
    def request(self, scenario, now):
        return {"transaction": {"amount": AMOUNTS[scenario]}}


class FakeState:
    def __init__(self):
        self.kv = MemoryKV()


AMOUNTS = {"genuine_routine": 850.0, "genuine_big_purchase": 18500.0, "sim_swap": 60000.0, "bot": 0.0, "genuine_new_phone": 1500.0,
           "genuine_travel": 900.0, "ato_new_device": 45000.0, "remote_access": 30000.0, "coerced": 95000.0}
DECISIONS = {"genuine_routine": "allow", "genuine_big_purchase": "challenge", "sim_swap": "block", "bot": "block"}


class FakeAuth:
    """Canned decisions, so these tests are about the gate and not about the model."""

    def __init__(self):
        self.state, self.demo, self.audited, self.verified = FakeState(), FakeDemo(), [], []
        self.n = 0

    def audit(self, record):
        self.audited.append(record)

    def run_demo(self, scenario):
        self.n += 1
        return {"scenario": scenario, "title": scenario, "story": "", "is_attack": scenario == "sim_swap",
                "request": {}, "response": {"decision_id": f"dec{self.n}", "user_id": "asha", "decision": DECISIONS[scenario],
                                            "amount": AMOUNTS[scenario]}}

    def verify_demo(self, decision_id, passed):
        self.verified.append((decision_id, passed))
        return {"decision_id": decision_id, "passed": passed, "decision": "allow" if passed else "block"}


@pytest.fixture
def paypal():
    return FakePayPal()


@pytest.fixture
def svc(paypal):
    return PayPalCheckout(FakeAuth(), PayPalClient("cid", "secret", transport=httpx.MockTransport(paypal)))


def start_open(svc, paypal):
    cid = svc.start("genuine_routine")["checkout"]["id"]
    order_id = svc.create_order(cid)["order_id"]
    paypal.approve(order_id)
    return cid, order_id


# ---------------------------------------------------------------------- the gate
def test_blocked_payment_never_reaches_paypal(svc, paypal):
    started = svc.start("sim_swap")
    assert started["checkout"]["gate"] == "blocked"
    with pytest.raises(GateClosed):
        svc.create_order(started["checkout"]["id"])
    with pytest.raises(GateClosed):
        svc.capture(started["checkout"]["id"], "ORDER1")
    assert paypal.requests == []


def test_challenged_payment_stays_out_of_paypal_until_the_step_up_passes(svc, paypal):
    cid = svc.start("genuine_big_purchase")["checkout"]["id"]
    with pytest.raises(GateClosed):
        svc.create_order(cid)
    assert paypal.requests == []
    assert svc.verify(cid, True)["checkout"]["gate"] == "open"
    assert svc.create_order(cid)["order_id"] == "ORDER1"


def test_failed_step_up_closes_the_gate_for_good(svc, paypal):
    cid = svc.start("genuine_big_purchase")["checkout"]["id"]
    assert svc.verify(cid, False)["checkout"]["gate"] == "blocked"
    with pytest.raises(GateClosed):
        svc.create_order(cid)
    with pytest.raises(GateClosed):
        svc.verify(cid, True)  # no second try
    assert paypal.requests == []


def test_a_login_has_nothing_to_pay(svc):
    with pytest.raises(ValueError):
        svc.start("bot")


def test_unknown_checkout(svc):
    with pytest.raises(KeyError):
        svc.create_order("nope")


# ---------------------------------------------------------------------- orders
def test_order_carries_the_decision_and_the_converted_amount(svc, paypal):
    started = svc.start("genuine_routine")
    assert started["checkout"]["amount"] == "10.00"  # 850 INR at the default rate of 85
    svc.create_order(started["checkout"]["id"])
    sent = json.loads(paypal.calls("/v2/checkout/orders")[0].content)
    assert sent == started["order_preview"]
    assert sent["intent"] == "CAPTURE"
    assert sent["purchase_units"][0]["custom_id"] == started["checkout"]["decision_id"]
    assert sent["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "10.00"}


def test_creating_an_order_twice_returns_the_same_order(svc, paypal):
    cid = svc.start("genuine_routine")["checkout"]["id"]
    assert svc.create_order(cid)["order_id"] == svc.create_order(cid)["order_id"]
    assert len(paypal.calls("/v2/checkout/orders")) == 1
    assert paypal.calls("/v2/checkout/orders")[0].headers["paypal-request-id"] == f"order-{cid}"


# ---------------------------------------------------------------------- capture
def test_capture(svc, paypal):
    cid, order_id = start_open(svc, paypal)
    out = svc.capture(cid, order_id)["checkout"]
    assert out["capture"] == {"id": "CAP1", "status": "COMPLETED", "amount": "10.00", "currency": "USD"}
    assert [r["kind"] for r in svc.auth.audited] == ["paypal_order_created", "paypal_captured"]


def test_capturing_twice_only_captures_once(svc, paypal):
    cid, order_id = start_open(svc, paypal)
    svc.capture(cid, order_id)
    svc.capture(cid, order_id)
    assert len(paypal.calls("/capture")) == 1


def test_capture_rejects_an_order_from_another_decision_without_calling_paypal(svc, paypal):
    cid, _ = start_open(svc, paypal)
    before = len(paypal.requests)
    with pytest.raises(OrderMismatch):
        svc.capture(cid, "SOMEOTHERORDER")
    assert len(paypal.requests) == before


def test_capture_rejects_an_order_the_buyer_has_not_approved(svc, paypal):
    cid = svc.start("genuine_routine")["checkout"]["id"]
    order_id = svc.create_order(cid)["order_id"]
    with pytest.raises(OrderMismatch):
        svc.capture(cid, order_id)
    assert paypal.calls("/capture") == []


def test_capture_rejects_an_order_whose_amount_changed_at_paypal(svc, paypal):
    cid, order_id = start_open(svc, paypal)
    paypal.orders[order_id]["purchase_units"][0]["amount"]["value"] = "1.00"
    with pytest.raises(OrderMismatch):
        svc.capture(cid, order_id)
    assert paypal.calls("/capture") == []


def test_declined_instrument_can_be_retried_with_a_new_request_id(svc, paypal):
    cid, order_id = start_open(svc, paypal)
    paypal.decline_next = True
    with pytest.raises(PayPalError) as e:
        svc.capture(cid, order_id)
    assert (e.value.issue, e.value.status, e.value.debug_id) == ("INSTRUMENT_DECLINED", 422, "dbg1")
    assert svc.capture(cid, order_id)["checkout"]["capture"]["status"] == "COMPLETED"
    ids = [r.headers["paypal-request-id"] for r in paypal.calls("/capture")]
    assert len(set(ids)) == 2


def test_already_captured_at_paypal_is_read_back_not_an_error(svc, paypal):
    cid, order_id = start_open(svc, paypal)
    svc.capture(cid, order_id)
    doc = svc._load(cid)
    doc["capture"] = None  # as if this instance lost the result of the first capture
    svc._save(doc)
    paypal.orders[order_id]["status"] = "APPROVED"  # passes the check; PayPal still refuses a second capture below
    real = paypal.__call__

    def refuse_second_capture(request):
        if request.url.path.endswith("/capture"):
            paypal.requests.append(request)
            paypal.orders[order_id]["status"] = "COMPLETED"
            return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]})
        return real(request)

    svc.client._http = httpx.Client(base_url=svc.client._http.base_url, transport=httpx.MockTransport(refuse_second_capture))
    assert svc.capture(cid, order_id)["checkout"]["capture"]["id"] == "CAP1"


# ---------------------------------------------------------------------- refund
def test_refund(svc, paypal):
    cid, order_id = start_open(svc, paypal)
    with pytest.raises(OrderMismatch):
        svc.refund(svc.start("genuine_routine")["checkout"]["id"])  # nothing captured there
    svc.capture(cid, order_id)
    assert svc.refund(cid)["checkout"]["refund"] == {"id": "REF1", "status": "COMPLETED"}
    svc.refund(cid)
    assert len(paypal.calls("/refund")) == 1


# ---------------------------------------------------------------------- the client
def test_token_is_reused_until_it_expires(paypal):
    c = PayPalClient("cid", "secret", transport=httpx.MockTransport(paypal))
    c.create_order({"intent": "CAPTURE", "purchase_units": [{"amount": {}}]}, "r1")
    c.create_order({"intent": "CAPTURE", "purchase_units": [{"amount": {}}]}, "r2")
    assert paypal.tokens == 1

    short = FakePayPal(expires_in=1)  # inside the safety margin: every call fetches a new one
    c = PayPalClient("cid", "secret", transport=httpx.MockTransport(short))
    c.create_order({"intent": "CAPTURE", "purchase_units": [{"amount": {}}]}, "r1")
    c.create_order({"intent": "CAPTURE", "purchase_units": [{"amount": {}}]}, "r2")
    assert short.tokens == 2


def test_a_revoked_token_is_replaced_once(paypal):
    c = PayPalClient("cid", "secret", transport=httpx.MockTransport(paypal))
    c.token()
    paypal.revoke_next = True
    assert c.create_order({"intent": "CAPTURE", "purchase_units": [{"amount": {}}]}, "r1")["id"] == "ORDER1"
    assert paypal.tokens == 2


def test_requests_go_to_the_sandbox_only(paypal):
    c = PayPalClient("cid", "secret", transport=httpx.MockTransport(paypal))
    c.token()
    assert paypal.requests[0].url.host == "api-m.sandbox.paypal.com"


def test_bad_credentials_are_reported_without_the_secret(paypal):
    c = PayPalClient("cid", "wrong-secret", transport=httpx.MockTransport(paypal))
    with pytest.raises(PayPalError) as e:
        c.token()
    assert e.value.status == 401 and e.value.issue == "invalid_client"
    assert "wrong-secret" not in str(e.value) and "wrong-secret" not in repr(c)
    assert PayPalCheckout(FakeAuth(), c).connection() == "bad_credentials"


def test_paypal_being_down_is_reported_as_unreachable():
    def down(request):
        raise httpx.ConnectError("no route", request=request)

    c = PayPalClient("cid", "secret", transport=httpx.MockTransport(down))
    assert PayPalCheckout(FakeAuth(), c).connection() == "unreachable"
    with pytest.raises(PayPalError) as e:
        c.token()
    assert e.value.status == 503


# ---------------------------------------------------------------------- without credentials
def test_without_credentials_decisions_work_and_orders_say_why_not():
    svc = PayPalCheckout(FakeAuth(), None)
    assert svc.connection() == "not_configured"
    started = svc.start("genuine_routine")
    assert started["order_preview"]["purchase_units"][0]["amount"]["value"] == "10.00"
    with pytest.raises(NotConfigured):
        svc.create_order(started["checkout"]["id"])
    assert svc.start("sim_swap")["checkout"]["gate"] == "blocked"


def test_blank_credentials_count_as_none(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "  ")
    assert client_from_env() is None
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "cid")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "secret")
    assert client_from_env().client_id == "cid"


def test_the_service_needs_the_auth_service():
    with pytest.raises(RuntimeError):
        PayPalCheckout(None)


# ---------------------------------------------------------------------- the API, with the real model making the decisions
@pytest.fixture(scope="module")
def api():
    from fastapi.testclient import TestClient

    from backend.app import REGISTRY, app
    saved = {k: os.environ.get(k) for k in ("PRAMAAN_SERVICES", "BIO_CALIB", "PRAMAAN_AUDIT_DB", "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET")}
    os.environ.update(PRAMAAN_SERVICES="biometrics,keystroke,auth,paypal", BIO_CALIB="ml/auth/artifacts/bio_calib.pkl",
                      PRAMAAN_AUDIT_DB="checkpoints/test_audit.sqlite", PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="")
    REGISTRY["errors"].clear()
    with TestClient(app) as c:
        fake = FakePayPal()
        REGISTRY["services"]["paypal"].client = PayPalClient("cid", "secret", transport=httpx.MockTransport(fake))
        yield c, fake
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_api_config_gives_the_client_id_and_never_the_secret(api):
    c, _ = api
    r = c.get("/v1/paypal/config")
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["client_id"], body["currency"]) == ("connected", "cid", "USD")
    assert "secret" not in r.text
    ids = {s["id"] for s in body["scenarios"]}
    assert "bot" not in ids and {"genuine_routine", "sim_swap"} <= ids  # a login has nothing to pay
    assert c.get("/health").json()["paypal"] == {"configured": True, "environment": "sandbox"}


def test_api_real_decisions_gate_real_routes(api):
    c, fake = api
    blocked = c.post("/v1/paypal/checkout/sim_swap").json()
    assert blocked["checkout"]["gate"] == "blocked" and blocked["run"]["response"]["decision"] == "block"
    before = len(fake.calls("/v2/checkout/orders"))
    r = c.post(f"/v1/paypal/checkout/{blocked['checkout']['id']}/order")
    assert r.status_code == 403 and "blocked" in r.json()["detail"]["message"]
    assert len(fake.calls("/v2/checkout/orders")) == before

    allowed = c.post("/v1/paypal/checkout/genuine_routine").json()
    assert allowed["checkout"]["gate"] == "open"
    cid = allowed["checkout"]["id"]
    order_id = c.post(f"/v1/paypal/checkout/{cid}/order").json()["order_id"]
    fake.approve(order_id)
    done = c.post(f"/v1/paypal/checkout/{cid}/capture", json={"order_id": order_id})
    assert done.status_code == 200 and done.json()["checkout"]["capture"]["status"] == "COMPLETED"
    assert c.post(f"/v1/paypal/checkout/{cid}/refund").json()["checkout"]["refund"]["status"] == "COMPLETED"


def test_api_step_up_loop(api):
    c, fake = api
    started = c.post("/v1/paypal/checkout/genuine_big_purchase").json()
    assert started["checkout"]["gate"] == "step_up"
    cid = started["checkout"]["id"]
    assert c.post(f"/v1/paypal/checkout/{cid}/order").status_code == 403
    assert c.post(f"/v1/paypal/checkout/{cid}/verify", json={"passed": True}).json()["checkout"]["gate"] == "open"
    assert c.post(f"/v1/paypal/checkout/{cid}/order").status_code == 200


def test_api_errors(api):
    c, fake = api
    assert c.post("/v1/paypal/checkout/bot").status_code == 422
    assert c.post("/v1/paypal/checkout/no_such_scenario").status_code in (404, 422)
    assert c.post("/v1/paypal/checkout/nope/order").status_code == 404
    started = c.post("/v1/paypal/checkout/genuine_routine").json()["checkout"]["id"]
    c.post(f"/v1/paypal/checkout/{started}/order")
    # the order id goes into a PayPal URL: anything but PayPal's own format is refused before that
    assert c.post(f"/v1/paypal/checkout/{started}/capture", json={"order_id": "../../v1/x"}).status_code == 422
    assert c.post(f"/v1/paypal/checkout/{started}/capture", json={"order_id": "OTHER1"}).status_code == 409
    order_id = c.post(f"/v1/paypal/checkout/{started}/order").json()["order_id"]
    fake.approve(order_id)
    fake.decline_next = True
    declined = c.post(f"/v1/paypal/checkout/{started}/capture", json={"order_id": order_id})
    assert declined.status_code == 422 and declined.json()["detail"]["issue"] == "INSTRUMENT_DECLINED"


def test_api_without_credentials_says_so(api):
    from backend.app import REGISTRY
    c, _ = api
    svc = REGISTRY["services"]["paypal"]
    saved, svc.client = svc.client, None
    try:
        assert c.get("/v1/paypal/config").json()["status"] == "not_configured"
        started = c.post("/v1/paypal/checkout/genuine_routine").json()
        r = c.post(f"/v1/paypal/checkout/{started['checkout']['id']}/order")
        assert r.status_code == 503 and "PAYPAL_CLIENT_ID" in r.json()["detail"]["message"]
    finally:
        svc.client = saved
