"""End-to-end HTTP latency benchmark against a running server.

    uvicorn backend.app:app --port 8000            # in one shell
    python -m backend.bench --url http://127.0.0.1:8000 --n 300

Client-side wall time per request over a keep-alive connection (includes JSON + HTTP overhead).
Writes backend/reports/serve_latency.md.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import httpx

from ml.models.biometrics.data import FEATURES
from ml.sim.generate import generate_demo

REPORT = Path("backend/reports/serve_latency.md")
RAW = ["event", "ts", "caller_kind", "call_video", "sms_sender_kind", "sms_has_link", "app_source", "payee_id",
       "payee_is_merchant", "payee_is_new", "payee_vpa_age_days", "payee_mule_score", "amount", "bio_pressure",
       "bio_swipe_velocity", "bio_tap_interval_ms", "bio_hesitation_ms", "bio_orientation_var"]


def timed(c: httpx.Client, method: str, path: str, **kw) -> float:
    t0 = time.perf_counter()
    r = c.request(method, path, **kw)
    r.raise_for_status()
    return 1000 * (time.perf_counter() - t0)


def session_events(c, n):
    events, sessions, users, _ = generate_demo("digital_arrest")
    user = {k: float(v) for k, v in users.iloc[0].items() if k == "avg_txn_amount" or k.startswith("bio_")}
    body = [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items() if k in RAW and v is not None and v == v}
            for r in events[RAW].astype(object).to_dict("records")]
    lat, pay, k = [], [], 0
    while len(lat) < n:
        sid = f"bench-{k}"
        c.post(f"/v1/session/{sid}/start", json={"user": {"user_id": f"bench-u{k}", **user}, "start_time": "2026-03-15T11:00:00"})
        for ev in body:
            if ev["event"] != "CALL_START":
                ev = {x: v for x, v in ev.items() if x not in ("caller_kind", "call_video")}
            ms = timed(c, "POST", f"/v1/session/{sid}/events", json=ev)
            (pay if ev["event"] == "PAYMENT_ATTEMPT" else lat).append(ms)
        k += 1
    return lat, pay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    res = {}
    with httpx.Client(base_url=a.url, timeout=30) as c:
        health = c.get("/health").json()
        res["GET /health"] = [timed(c, "GET", "/health") for _ in range(a.n)]
        ev, pay = session_events(c, a.n)
        res["POST /v1/session/{id}/events (non-payment)"] = ev
        res["POST /v1/session/{id}/events (PAYMENT_ATTEMPT: GRU + fusion + policy)"] = pay
        t = {"timestamp": "2022-09-12T10:00:00", "from_bank": "070", "from_account": "100428660", "to_bank": "001",
             "to_account": "8000EBD30", "amount_paid": 5000, "amount_received": 5000, "payment_currency": "US Dollar",
             "receiving_currency": "US Dollar", "payment_format": "ACH", "record": False}
        res["POST /v1/gnn/score"] = [timed(c, "POST", "/v1/gnn/score", json=t) for _ in range(a.n)]
        g = [dict(zip(FEATURES, map(float, rng.normal(size=len(FEATURES))))) for _ in range(40)]
        c.post("/v1/biometrics/enroll", json={"user_id": "bench", "gestures": g})
        res["POST /v1/biometrics/verify (20 gestures)"] = [timed(c, "POST", "/v1/biometrics/verify",
                                                                 json={"user_id": "bench", "gestures": g[:20]}) for _ in range(a.n)]
        row = {"TransactionAmt": 120.0, "ProductCD": "W", "card4": "visa"}
        res["POST /v1/tabular/score (1 txn)"] = [timed(c, "POST", "/v1/tabular/score", json={"transactions": [row]}) for _ in range(a.n)]
        res["POST /v1/tabular/score (100 txns)"] = [timed(c, "POST", "/v1/tabular/score", json={"transactions": [row] * 100})
                                                    for _ in range(max(20, a.n // 10))]
    lines = ["# API latency (end-to-end HTTP, keep-alive, single client)", "",
             f"Server device: {health['device']}; services: {', '.join(health['loaded'])}. Client-side wall time incl. "
             "JSON/HTTP overhead, localhost, RTX 4070 laptop.", "",
             "| endpoint | n | p50 ms | p95 ms | p99 ms |", "|---|---|---|---|---|"]
    for k, v in res.items():
        v = np.asarray(v)
        lines.append(f"| {k} | {len(v)} | {np.percentile(v, 50):.1f} | {np.percentile(v, 95):.1f} | {np.percentile(v, 99):.1f} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
