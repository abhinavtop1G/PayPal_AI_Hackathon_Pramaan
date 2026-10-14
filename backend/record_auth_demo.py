"""Record the authentication demo scenarios for the console's offline mode (no API needed to present).

    python -m backend.record_auth_demo        # -> frontend/public/data/auth_demo.json

Runs every scenario through the real service in-process (touch biometrics + payee intelligence + auth), and for each
challenged scenario records what happens when the challenge is passed and when it is failed.
"""
import json
import os
from pathlib import Path

OUT = Path("frontend/public/data/auth_demo.json")


def main():
    os.environ.setdefault("BIOS_SERVICES", "biometrics,campaign,auth")
    os.environ.setdefault("BIOS_AUDIT_DB", "checkpoints/record_audit.sqlite")
    from fastapi.testclient import TestClient
    from backend.app import app
    with TestClient(app) as c:
        scenarios = c.get("/v1/auth/scenarios").json()
        runs, outcomes = {}, {}
        for s in scenarios:
            run = c.post(f"/v1/auth/demo/{s['id']}", json={}).json()
            runs[s["id"]] = run
            if run["response"]["decision"] == "challenge":
                outcomes[s["id"]] = {}
                for passed in (True, False):
                    again = c.post(f"/v1/auth/demo/{s['id']}", json={}).json()
                    if again["response"]["decision"] != "challenge":
                        continue
                    outcomes[s["id"]]["pass" if passed else "fail"] = c.post(
                        "/v1/auth/demo/verify", json={"decision_id": again["response"]["decision_id"], "passed": passed}).json()
            r = run["response"]
            print(f"{s['id']:22s} {r['decision']:9s} {str(r['challenge_type']):13s} risk={r['risk_score']:.4f}  {r['latency_ms']} ms")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"scenarios": scenarios, "runs": runs, "outcomes": outcomes}, ensure_ascii=False), encoding="utf-8")
    print(f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
