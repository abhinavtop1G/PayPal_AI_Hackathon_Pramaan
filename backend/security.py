"""API security for the cloud service: API keys, HMAC request signing with replay protection, rate limiting.

All three are switched on by environment variables (in Cloud Run, from Secret Manager):
    PRAMAAN_API_KEYS      comma-separated keys; requests to /v1/* must send `X-API-Key`
    PRAMAAN_HMAC_SECRET   requests must send `X-Timestamp` (unix seconds, within 5 minutes) and
                       `X-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>`;
                       a signature is accepted once (replay protection)
    PRAMAAN_RATE_LIMIT    sustained requests per second per key (or client IP), burst = 2x (default 50)
    PRAMAAN_OPEN_PATHS    comma-separated path prefixes that skip key/signature checks (the public demo console)
Unset keys/secret = open development mode, reported by /health. TLS terminates at the load balancer / Cloud Run.
Implemented as plain ASGI middleware so the body can be read for the signature and replayed to the endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from collections import OrderedDict

EXEMPT = ("/health", "/docs", "/openapi.json", "/redoc")
WINDOW_S = 300


def sign(secret: str, body: bytes, ts: int | None = None) -> dict:
    """Headers a client sends for a signed request (used by tests, the bench and SDK examples)."""
    ts = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Timestamp": str(ts), "X-Signature": f"sha256={mac}"}


class TokenBucket:
    def __init__(self, rate: float, burst: float):
        self.rate, self.burst = rate, burst
        self.b: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            tokens, last = self.b.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            ok = tokens >= 1
            self.b[key] = (tokens - 1 if ok else tokens, now)
            if len(self.b) > 50000:
                self.b.clear()
            return ok


def _config() -> dict:
    return {"keys": {k.strip() for k in os.environ.get("PRAMAAN_API_KEYS", "").split(",") if k.strip()},
            "secret": os.environ.get("PRAMAAN_HMAC_SECRET") or None,
            "rate": float(os.environ.get("PRAMAAN_RATE_LIMIT", "50")),
            "open_paths": tuple(p.strip() for p in os.environ.get("PRAMAAN_OPEN_PATHS", "").split(",") if p.strip())}


def status() -> dict:
    c = _config()
    return {"api_keys": bool(c["keys"]), "hmac_signing": bool(c["secret"]), "rate_limit_rps": c["rate"],
            "open_paths": list(c["open_paths"]), "mode": "secured" if (c["keys"] or c["secret"]) else "open (development)"}


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app
        c = _config()
        self.keys, self.secret, self.open_paths = c["keys"], c["secret"], c["open_paths"]
        self.bucket = TokenBucket(c["rate"], 2 * c["rate"])
        self.seen: OrderedDict[str, float] = OrderedDict()
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not path.startswith("/v1/") or path.startswith(EXEMPT):
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        client = headers.get("x-api-key") or (scope.get("client") or ("?",))[0]
        if not self.bucket.allow(client):
            return await _reject(send, 429, "rate limit exceeded")
        if self.open_paths and path.startswith(self.open_paths):
            return await self.app(scope, receive, send)
        if self.keys and not any(hmac.compare_digest(headers.get("x-api-key", ""), k) for k in self.keys):
            return await _reject(send, 401, "missing or invalid X-API-Key")
        if not self.secret:
            return await self.app(scope, receive, send)

        body = b""
        more = True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
        ts, sig = headers.get("x-timestamp", ""), headers.get("x-signature", "")
        try:
            if abs(time.time() - int(ts)) > WINDOW_S:
                return await _reject(send, 401, "request timestamp outside the 5-minute window")
        except ValueError:
            return await _reject(send, 401, "missing X-Timestamp")
        want = "sha256=" + hmac.new(self.secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, want):
            return await _reject(send, 401, "invalid X-Signature")
        with self.lock:
            now = time.time()
            while self.seen and next(iter(self.seen.values())) < now - WINDOW_S:
                self.seen.popitem(last=False)
            if sig in self.seen:
                return await _reject(send, 409, "replayed request")
            self.seen[sig] = now

        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        return await self.app(scope, replay, send)


async def _reject(send, status: int, detail: str):
    payload = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]})
    await send({"type": "http.response.body", "body": payload})
