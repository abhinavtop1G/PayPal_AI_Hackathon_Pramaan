"""Record what the frontend plays back when no API is running.

    python -m backend.record_demo                    # everything
    python -m backend.record_demo --only demos       # scripted scenarios x personas -> frontend/src/data/
    python -m backend.record_demo --only fleet       # a day of simulator test sessions -> frontend/public/data/fleet.json
    python -m backend.record_demo --only campaign    # payee-side cases + money-flow graphs -> frontend/public/data/campaign.json

Demo files are the exact `POST /v1/demo/{typology}?persona=` responses from the real models. The fleet runs the
session service directly over the simulator's held-out test sessions (one shared alert policy, events in time order,
so anti-fatigue rules act across customers as they would live). Campaign data is `/v1/campaign/cases` and
`/v1/campaign/cases/{id}/graph` after replaying the synthetic ledger.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

# each scam with its genuine look-alike (same user, similar workflow)
TYPOLOGIES = ["digital_arrest", "hospital_emergency", "voice_clone_relative", "genuine_urgent_family",
              "fake_kyc_apk", "bank_app_update", "investment_task", "legit_investing"]
PERSONAS = ["senior", "student", "professional"]
FRONT = Path("frontend")


def _dump(path: Path, body) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def record_demos(c, typologies, personas) -> None:
    for persona in personas:
        for typ in typologies:
            c.post("/v1/admin/reset", params={"services": "session"})  # every replay starts from a fresh alert-policy history (all demos share one user)
            r = c.post(f"/v1/demo/{typ}", params={"persona": persona})
            r.raise_for_status()
            body = r.json()
            body["session_id"] = f"demo-{persona}-{typ}"  # drop the timestamp suffix so re-recording gives a stable file
            name = f"demo_{typ}.json" if persona == "senior" else f"demo_{persona}_{typ}.json"
            path = FRONT / "src" / "data" / name
            path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            first = next((e for e in body["timeline"] if e["decision"] and e["decision"]["notify"]), None)
            print(f"{path}: {len(body['timeline'])} events, first alert: "
                  f"{first and (first['ts_min'], first['decision']['action'], first['decision']['fused_risk'])}")


def record_fleet(hours: float = 12.0, start_day: float = 80.0) -> None:
    """Run `hours` of held-out simulator sessions through the session pipeline, interleaved in real time order."""
    from backend.schemas import SessionEvent
    from backend.session_service import SessionService
    from ml.models.workflow.data import SIM_DIR

    sessions = pd.read_parquet(SIM_DIR / "sessions.parquet")
    events = pd.read_parquet(SIM_DIR / "events.parquet")
    users = pd.read_parquet(SIM_DIR / "users.parquet").set_index("user_id")
    t0 = sessions["start_time"].min().normalize() + pd.Timedelta(days=start_day)
    pick = sessions[(sessions["start_time"] >= t0) & (sessions["start_time"] < t0 + pd.Timedelta(hours=hours))]
    ev = events[events["session_id"].isin(pick["session_id"])].copy()
    meta = pick.set_index("session_id")
    ev["abs"] = ev["session_id"].map(meta["start_time"]) + pd.to_timedelta(ev["ts"], unit="s")
    ev = ev.sort_values(["abs", "session_id", "ts"], kind="stable")

    svc = SessionService(os.environ.get("RAKSHAM_DEVICE", "cuda"))
    keep = set(SessionEvent.model_fields)
    out: dict[str, dict] = {}
    for sid, m in meta.iterrows():
        u = users.loc[m["user_id"]]
        svc.start(sid, {"user_id": m["user_id"], **u.to_dict()}, m["start_time"])
        ext = m.get("extraction_ts")
        out[sid] = {"session_id": sid, "typology": m["typology"], "is_scam": bool(m["is_scam"]),
                    "extraction_ts_min": None if pd.isna(ext) else round(float(ext) / 60, 2),
                    "start_time": pd.Timestamp(m["start_time"]).isoformat(),
                    "user": {"id": m["user_id"], "avg_txn_amount": round(float(u["avg_txn_amount"]), 2), "age_group": u["age_group"]},
                    "timeline": []}
    for r in ev.itertuples(index=False):
        row = r._asdict()
        x = {k: (None if (v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA) else v) for k, v in row.items() if k in keep}
        ref = row.get("bio_ref")
        if isinstance(ref, str) and svc.bio_bank is not None:
            x["gestures"] = svc.bio_bank.resolve(ref)[1]  # the device sends the real gestures behind the window
        x = SessionEvent(**{k: v for k, v in x.items() if v is not None}).model_dump(exclude_none=True)
        res = svc.add_event(r.session_id, x)
        res.pop("latency_ms", None)
        inp = {k: v for k, v in x.items() if not k.startswith("bio_") and k != "gestures"}
        if "gestures" in x:
            inp["gestures_n"] = len(x["gestures"])
        out[r.session_id]["timeline"].append({"ts_min": round(float(r.ts) / 60, 2), "true_stage": r.stage, "input": inp, "latency_ms": 0, **res})

    body = {"window": {"start": t0.isoformat(), "hours": hours},
            "note": "Held-out simulator test sessions (scams oversampled to 20% of sessions for training; real prevalence is far lower).",
            "sessions": sorted(out.values(), key=lambda s: s["start_time"])}
    path = FRONT / "public" / "data" / "fleet.json"
    _dump(path, body)
    n = len(body["sessions"])
    held = sum(any(e["decision"] and e["decision"]["action"] == "hold" and e["decision"]["notify"] for e in s["timeline"]) for s in body["sessions"])
    print(f"{path}: {n} sessions, {sum(s['is_scam'] for s in body['sessions'])} scams, {held} held, "
          f"{path.stat().st_size / 1e6:.1f} MB")


def record_campaign(c, until_day: float = 60.0, top: int = 12) -> None:
    c.post("/v1/campaign/demo/load", json={"until_day": until_day, "n_sessions": 3000, "ambient_scale": 0.4}).raise_for_status()
    cases = c.get("/v1/campaign/cases", params={"top": top}).json()
    graphs = {k["case_id"]: c.get(f"/v1/campaign/cases/{k['case_id']}/graph").json() for k in cases["cases"]}
    path = FRONT / "public" / "data" / "campaign.json"
    _dump(path, {"until_day": until_day, **cases, "graphs": graphs})
    print(f"{path}: {len(cases['cases'])} cases, {path.stat().st_size / 1e6:.2f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=["demos", "fleet", "campaign"], default=["demos", "fleet", "campaign"])
    ap.add_argument("--typology", nargs="+", default=TYPOLOGIES)
    ap.add_argument("--persona", nargs="+", default=PERSONAS)
    ap.add_argument("--fleet-hours", type=float, default=12.0)
    args = ap.parse_args()
    os.environ.setdefault("RAKSHAM_SERVICES", "campaign,session")

    from fastapi.testclient import TestClient
    from backend.app import app

    with TestClient(app) as c:
        if "demos" in args.only:
            record_demos(c, args.typology, args.persona)
        if "campaign" in args.only:
            record_campaign(c)
    if "fleet" in args.only:
        record_fleet(args.fleet_hours)


if __name__ == "__main__":
    main()
