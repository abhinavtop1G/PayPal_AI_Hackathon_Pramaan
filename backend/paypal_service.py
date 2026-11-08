"""PayPal checkout behind PRAMAAN: PayPal's Orders API is reached only for a payment the risk decision lets through.

    start(scenario)     PRAMAAN decides first. A blocked or challenged payment has no PayPal order.
    verify(id, passed)  the step-up result opens the gate, or closes it for good.
    create_order(id)    POST /v2/checkout/orders: the amount comes from the decision, the decision id goes in custom_id.
    capture(id, order)  re-reads the order from PayPal, checks it is this decision's, then captures it.
    refund(id)          POST /v2/payments/captures/{id}/refund, for fraud reported after the money moved.

The gate is enforced here, on the server, so a modified browser can't reach PayPal for a blocked payment. Requests go to
PayPal's sandbox and nowhere else: there is deliberately no setting that points this at live money.

Credentials come from PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET. Without them the risk decisions still work and the page
shows the order that would be sent. The client id is public (the browser SDK needs it); the secret never leaves this file.
"""
from __future__ import annotations

import os
import threading
import time
import uuid

import httpx

SANDBOX_API = "https://api-m.sandbox.paypal.com"
CURRENCY = "USD"  # PayPal's supported currencies don't include INR, the currency the risk model works in
CHECKOUT_TTL_S = 3600
TOKEN_MARGIN_S = 60


class PayPalError(Exception):
    """PayPal refused a request, or could not be reached."""

    def __init__(self, message: str, status: int, issue: str | None = None, debug_id: str | None = None):
        super().__init__(message)
        self.status, self.issue, self.debug_id = status, issue, debug_id


class GateClosed(Exception):
    """The risk decision does not allow this payment to reach PayPal."""


class NotConfigured(Exception):
    """No sandbox credentials are set."""


class OrderMismatch(Exception):
    """The PayPal order is not the one this decision created, or is not ready to capture."""


class PayPalClient:
    """A thin client for the parts of PayPal's REST API used here. OAuth2 token cached until shortly before it expires."""

    def __init__(self, client_id: str, client_secret: str, transport: httpx.BaseTransport | None = None, timeout: float = 20.0):
        self.client_id = client_id
        self._secret = client_secret
        self._http = httpx.Client(base_url=SANDBOX_API, timeout=timeout, transport=transport)
        self._token: str | None = None
        self._token_expires = 0.0
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"PayPalClient(client_id={self.client_id!r})"

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expires:
                return self._token
            try:
                r = self._http.post("/v1/oauth2/token", auth=(self.client_id, self._secret), data={"grant_type": "client_credentials"})
            except httpx.HTTPError as e:
                raise PayPalError(f"Could not reach PayPal ({type(e).__name__}). Check your connection and try again.", 503, "UNREACHABLE") from e
            if r.status_code != 200:
                raise PayPalError("PayPal rejected the sandbox credentials", r.status_code, _json(r).get("error") or "AUTHENTICATION_FAILED")
            body = r.json()
            self._token = body["access_token"]
            self._token_expires = time.time() + float(body.get("expires_in", 0)) - TOKEN_MARGIN_S
            return self._token

    def _forget_token(self) -> None:
        with self._lock:
            self._token, self._token_expires = None, 0.0

    def _call(self, method: str, path: str, *, body: dict | None = None, request_id: str | None = None) -> dict:
        headers = {"Prefer": "return=representation"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id  # a retry returns the first result instead of acting twice
        for attempt in (0, 1):
            headers["Authorization"] = f"Bearer {self.token()}"
            try:
                r = self._http.request(method, path, json=body, headers=headers)
            except httpx.HTTPError as e:
                raise PayPalError(f"Could not reach PayPal ({type(e).__name__}). Check your connection and try again.", 503, "UNREACHABLE") from e
            if r.status_code == 401 and attempt == 0:  # the token was revoked or expired early: get a new one, once
                self._forget_token()
                continue
            break
        if r.is_success:
            return r.json() if r.content else {}
        err = _json(r)
        details = err.get("details") or [{}]
        raise PayPalError(err.get("message") or f"PayPal answered {r.status_code}", r.status_code,
                          details[0].get("issue") or err.get("name"), err.get("debug_id"))

    def create_order(self, order: dict, request_id: str) -> dict:
        return self._call("POST", "/v2/checkout/orders", body=order, request_id=request_id)

    def get_order(self, order_id: str) -> dict:
        return self._call("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id: str, request_id: str) -> dict:
        return self._call("POST", f"/v2/checkout/orders/{order_id}/capture", body={}, request_id=request_id)

    def refund_capture(self, capture_id: str, request_id: str) -> dict:
        return self._call("POST", f"/v2/payments/captures/{capture_id}/refund", body={}, request_id=request_id)


def _json(r: httpx.Response) -> dict:
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _capture_of(order: dict) -> dict | None:
    """The capture inside an order resource, or None if the order has none yet."""
    for unit in order.get("purchase_units") or []:
        for cap in ((unit.get("payments") or {}).get("captures")) or []:
            return cap
    return None


def client_from_env() -> PayPalClient | None:
    cid, secret = os.environ.get("PAYPAL_CLIENT_ID", "").strip(), os.environ.get("PAYPAL_CLIENT_SECRET", "").strip()
    return PayPalClient(cid, secret) if cid and secret else None


class PayPalCheckout:
    def __init__(self, auth, client: PayPalClient | None = None):
        if auth is None:
            raise RuntimeError("the paypal service needs the auth service: it gates payments on PRAMAAN's decisions")
        self.auth = auth
        self.client = client
        self.inr_per_usd = float(os.environ.get("PAYPAL_INR_PER_USD", "85"))

    # ------------------------------------------------------------------ what the page needs
    def info(self) -> dict:
        return {"configured": self.client is not None, "environment": "sandbox"}

    def connection(self) -> str:
        if self.client is None:
            return "not_configured"
        try:
            self.client.token()
            return "connected"
        except PayPalError as e:
            return "unreachable" if e.issue == "UNREACHABLE" else "bad_credentials"

    def config(self) -> dict:
        from ml.auth.demo import SCENARIOS
        now = time.time()
        scenarios = []
        for sid, (title, story, is_attack) in SCENARIOS.items():
            amount = float((self.auth.demo.request(sid, now).get("transaction") or {}).get("amount") or 0)
            if amount > 0:  # logins have nothing to pay for
                scenarios.append({"id": sid, "title": title, "story": story, "is_attack": is_attack,
                                  "amount_inr": amount, "amount": self._usd(amount)})
        return {"status": self.connection(), "environment": "sandbox", "client_id": self.client.client_id if self.client else None,
                "currency": CURRENCY, "inr_per_usd": self.inr_per_usd, "scenarios": scenarios}

    def _usd(self, amount_inr: float) -> str:
        return f"{amount_inr / self.inr_per_usd:.2f}"

    # ------------------------------------------------------------------ the flow
    def start(self, scenario: str) -> dict:
        """PRAMAAN decides the payment. Nothing has been sent to PayPal when this returns."""
        if scenario == "custom":
            raise ValueError("pick one of the demo scenarios")
        run = self.auth.run_demo(scenario)
        r = run["response"]
        if not r.get("amount"):
            raise ValueError(f"'{scenario}' is a login: there is nothing to pay")
        gate = {"allow": "open", "challenge": "step_up", "block": "blocked"}[r["decision"]]
        doc = {"id": uuid.uuid4().hex, "scenario": scenario, "title": run["title"], "decision_id": r["decision_id"],
               "user_id": r["user_id"], "gate": gate, "amount_inr": r["amount"], "amount": self._usd(r["amount"]),
               "currency": CURRENCY, "order_id": None, "capture": None, "refund": None, "capture_attempts": 0}
        self._save(doc)
        return {"checkout": _view(doc), "run": run, "order_preview": self._order_body(doc)}

    def verify(self, checkout_id: str, passed: bool) -> dict:
        doc = self._load(checkout_id)
        if doc["gate"] != "step_up":
            raise GateClosed(f"this payment is not waiting for a step-up (gate: {doc['gate']})")
        outcome = self.auth.verify_demo(doc["decision_id"], passed)
        doc["gate"] = "open" if outcome["decision"] == "allow" else "blocked"
        self._save(doc)
        return {"checkout": _view(doc), "outcome": outcome}

    def create_order(self, checkout_id: str) -> dict:
        doc = self._load(checkout_id)
        self._require_open(doc)
        if doc["order_id"]:
            return {"checkout": _view(doc), "order_id": doc["order_id"]}
        client = self._require_client()
        order = client.create_order(self._order_body(doc), request_id=f"order-{doc['id']}-{doc['capture_attempts']}")
        doc["order_id"] = order["id"]
        self._save(doc)
        self._audit(doc, "paypal_order_created")
        return {"checkout": _view(doc), "order_id": doc["order_id"]}

    def capture(self, checkout_id: str, order_id: str) -> dict:
        doc = self._load(checkout_id)
        self._require_open(doc)
        if doc["capture"]:
            return {"checkout": _view(doc)}
        client = self._require_client()
        if order_id != doc["order_id"]:
            raise OrderMismatch("this PayPal order does not belong to this decision")
        order = client.get_order(order_id)
        self._check_order(doc, order)
        doc["capture_attempts"] += 1
        self._save(doc)
        try:
            # a new id per attempt: after a declined card the buyer retries, and the retry must really run
            result = client.capture_order(order_id, request_id=f"capture-{doc['id']}-{doc['capture_attempts']}")
        except PayPalError as e:
            if e.issue != "ORDER_ALREADY_CAPTURED":
                raise
            result = client.get_order(order_id)
        cap = _capture_of(result)
        if cap is None:
            raise PayPalError("PayPal's capture response had no capture in it", 502, "NO_CAPTURE", result.get("debug_id"))
        if cap.get("status") in ("DECLINED", "FAILED"):
            # PayPal can complete the order and still refuse the money. That is no receipt, and paying again needs a new order.
            self._audit(doc, "paypal_capture_declined", capture_id=cap.get("id"), status=cap.get("status"))
            doc["order_id"] = None
            self._save(doc)
            raise PayPalError("PayPal declined this payment, so nothing was charged. Try again with another card.", 422,
                              "CAPTURE_DECLINED", result.get("debug_id"))
        doc["capture"] = {"id": cap.get("id"), "status": cap.get("status"), "amount": (cap.get("amount") or {}).get("value"),
                          "currency": (cap.get("amount") or {}).get("currency_code")}
        self._save(doc)
        self._audit(doc, "paypal_captured", capture_id=cap.get("id"), status=cap.get("status"))
        return {"checkout": _view(doc)}

    def refund(self, checkout_id: str) -> dict:
        doc = self._load(checkout_id)
        if not doc["capture"]:
            raise OrderMismatch("nothing has been captured for this payment")
        if doc["refund"]:
            return {"checkout": _view(doc)}
        client = self._require_client()
        result = client.refund_capture(doc["capture"]["id"], request_id=f"refund-{doc['id']}")
        doc["refund"] = {"id": result.get("id"), "status": result.get("status")}
        self._save(doc)
        self._audit(doc, "paypal_refunded", refund_id=result.get("id"), status=result.get("status"))
        return {"checkout": _view(doc)}

    # ------------------------------------------------------------------ helpers
    def _order_body(self, doc: dict) -> dict:
        return {"intent": "CAPTURE", "purchase_units": [{
            "custom_id": doc["decision_id"],  # ties the PayPal transaction to the decision and its signals
            "description": "PRAMAAN demo checkout",
            "amount": {"currency_code": doc["currency"], "value": doc["amount"]}}]}

    @staticmethod
    def _check_order(doc: dict, order: dict) -> None:
        """Trust PayPal's copy of the order over anything the browser said."""
        units = order.get("purchase_units") or [{}]
        amount = (units[0].get("amount") or {})
        if units[0].get("custom_id") != doc["decision_id"]:
            raise OrderMismatch("this PayPal order was not created for this decision")
        if amount.get("value") != doc["amount"] or amount.get("currency_code") != doc["currency"]:
            raise OrderMismatch("the PayPal order's amount does not match the amount PRAMAAN decided on")
        if order.get("status") != "APPROVED":
            raise OrderMismatch(f"the buyer has not approved this order (status: {order.get('status')})")

    @staticmethod
    def _require_open(doc: dict) -> None:
        if doc["gate"] == "blocked":
            raise GateClosed("PRAMAAN blocked this payment, so it can't reach PayPal")
        if doc["gate"] == "step_up":
            raise GateClosed("this payment needs its step-up to pass before it can reach PayPal")

    def _require_client(self) -> PayPalClient:
        if self.client is None:
            raise NotConfigured("no PayPal sandbox credentials are set (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)")
        return self.client

    def _load(self, checkout_id: str) -> dict:
        doc = self.auth.state.kv.get(f"paypal:{checkout_id}")
        if doc is None:
            raise KeyError(f"no checkout {checkout_id} (unknown or expired)")
        return doc

    def _save(self, doc: dict) -> None:
        self.auth.state.kv.set(f"paypal:{doc['id']}", doc, ttl=CHECKOUT_TTL_S)

    def _audit(self, doc: dict, kind: str, **extra) -> None:
        if self.auth.audit is not None:
            self.auth.audit({"kind": kind, "ts": time.time(), "decision_id": doc["decision_id"], "user_id": doc["user_id"],
                             "order_id": doc["order_id"], "amount": doc["amount"], "currency": doc["currency"], **extra})


def _view(doc: dict) -> dict:
    return {k: doc[k] for k in ("id", "scenario", "decision_id", "gate", "amount", "amount_inr", "currency", "order_id", "capture", "refund")}
