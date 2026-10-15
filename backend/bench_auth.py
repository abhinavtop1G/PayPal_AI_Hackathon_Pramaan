"""End-to-end latency of POST /v1/authenticate against a running server (local or Cloud Run).

    uvicorn backend.app:app --port 8000                                   # PRAMAAN_SERVICES=biometrics,campaign,auth
    python -m backend.bench_auth --url http://127.0.0.1:8000 --n 300
    PRAMAAN_API_KEY=... PRAMAAN_HMAC_SECRET=... python -m backend.bench_auth --url https://pramaan-auth-xxxx.a.run.app

Client-side wall time per request over a keep-alive connection, including JSON, HTTP, TLS (if https) and, when the
secrets are set, API-key + HMAC verification. Writes backend/reports/auth_latency.md.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
import numpy as np

from backend.security import sign
from ml.auth.demo import PACK

REPORT = Path("backend/reports/auth_latency.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args()
    key, secret = os.environ.get("PRAMAAN_API_KEY"), os.environ.get("PRAMAAN_HMAC_SECRET")
    pack = json.loads(PACK.read_text())
    rng = np.random.default_rng(0)

    def body(k: int, gestures: bool) -> dict:
        return {"user_id": f"bench-{k % 200}", "device": {"device_id": f"bench-dev-{k % 200}", "platform": "android"},
                "network": {"ip": f"49.36.{k % 250}.{1 + k % 200}", "city": "Pune", "lat": 18.52, "lon": 73.85},
                "behaviour": {"gestures": pack["windows"]["normal"][k % 24] if gestures else None,
                              "time_to_submit_s": 15.0, "input_events": 30},
                "transaction": {"amount": float(rng.lognormal(6.5, 0.7)), "payee_id": f"payee-{k % 37}"}}

    def post(c, path: str, b: dict) -> httpx.Response:
        raw = json.dumps(b).encode()
        h = {"Content-Type": "application/json"}
        if key:
            h["X-API-Key"] = key
        if secret:
            h.update(sign(secret, raw))
        r = c.post(path, content=raw, headers=h)
        r.raise_for_status()
        return r

    def call(c, b) -> float:
        t0 = time.perf_counter()
        r = post(c, "/v1/authenticate", b)
        if b["behaviour"]["gestures"] and r.json()["features"]["bio_dev"] is None:
            raise RuntimeError("touch gestures were sent but not verified (user not enrolled?)")
        return 1000 * (time.perf_counter() - t0)

    res = {}
    with httpx.Client(base_url=a.url, timeout=30) as c:
        health = c.get("/health").json()
        if health.get("auth", {}) and health["auth"].get("touch_biometrics"):  # enrol the bench users' touch profile
            for u in range(200):
                post(c, "/v1/biometrics/enroll", {"user_id": f"bench-{u}", "gestures": pack["enrolment"]})
        for _ in range(10):
            call(c, body(0, False))  # warm-up
        res["POST /v1/authenticate (no touch data)"] = [call(c, body(k, False)) for k in range(a.n)]
        res["POST /v1/authenticate (+10 touch gestures verified)"] = [call(c, body(k, True)) for k in range(a.n)]
    lines = ["# /v1/authenticate latency (end-to-end HTTP, keep-alive, single client)", "",
             f"Target: {a.url}; device: {health.get('device')}; services: {', '.join(health.get('loaded', []))}; "
             f"security: {health.get('security', {}).get('mode')}; state: {(health.get('auth') or {}).get('state_backend')}.",
             "Client-side wall time incl. JSON/HTTP" + (" + API key + HMAC check" if key or secret else "") + ".", "",
             "| endpoint | n | p50 ms | p95 ms | p99 ms |", "|---|---|---|---|---|"]
    for k, v in res.items():
        v = np.asarray(v)
        lines.append(f"| {k} | {len(v)} | {np.percentile(v, 50):.1f} | {np.percentile(v, 95):.1f} | {np.percentile(v, 99):.1f} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
