"""RAKSHAM scam-detection API.

    uvicorn backend.app:app --port 8000          # docs at http://127.0.0.1:8000/docs

Services load at startup; one that fails (e.g. dataset missing) is reported in /health and its
endpoints return 503, the rest keep working. Select with RAKSHAM_SERVICES=campaign,session,gnn,biometrics,tabular
and the device with RAKSHAM_DEVICE=cuda|cpu. The payee-side `campaign` service loads before `session`, which
uses it to fill in the payee risk of a payment.
"""
import os
import time
import traceback
from contextlib import asynccontextmanager

import pandas as pd
import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from ml.sim.generate import generate_demo

from .schemas import (ConsentCheck, DemoLoad, Gestures, HoldRequest, LedgerTransfer, PayeeQuery, PSIDemo, SessionEvent,
                      SessionStart, TabularRequest, Transfer)

SERVICES = ("campaign", "session", "gnn", "biometrics", "tabular")
REGISTRY: dict = {"services": {}, "errors": {}, "load_seconds": {}}


def _load(name: str, device: str):
    if name == "campaign":
        from .campaign_service import CampaignService
        return CampaignService(os.environ.get("RAKSHAM_CAMPAIGN_DIR", "ml/campaign/artifacts"))
    if name == "session":
        from .session_service import SessionService
        return SessionService(device, campaign=REGISTRY["services"].get("campaign"))
    if name == "gnn":
        from .gnn_service import GNNService
        return GNNService(os.environ.get("RAKSHAM_GNN_ATTN", "diff"), device)
    if name == "biometrics":
        from .bio_service import BioService
        return BioService(device)
    from .tabular_service import TabularService
    return TabularService()  # always CPU (see tabular_service docstring)


@asynccontextmanager
async def lifespan(app: FastAPI):
    device = os.environ.get("RAKSHAM_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    REGISTRY["device"] = device
    wanted = [s.strip() for s in os.environ.get("RAKSHAM_SERVICES", ",".join(SERVICES)).split(",") if s.strip()]
    for name in wanted:
        t0 = time.perf_counter()
        try:
            REGISTRY["services"][name] = _load(name, device)
        except Exception as e:  # keep the API up; report what failed
            REGISTRY["errors"][name] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        REGISTRY["load_seconds"][name] = round(time.perf_counter() - t0, 2)
    yield
    REGISTRY["services"].clear()


app = FastAPI(title="RAKSHAM scam-detection API", version="0.1.0", lifespan=lifespan,
              description="Workflow-aware UPI scam detection: session pipeline, mule GNN, behavioural biometrics, "
                          "transaction risk. Simulator stand-ins are documented per endpoint.")


# the demo frontend (Next.js dev server) calls the API from the browser; override with a comma-separated list
app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Process-Time-ms"],
                   allow_origins=[o.strip() for o in os.environ.get("RAKSHAM_CORS_ORIGINS",
                                                                    "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()])


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-ms"] = f"{1000 * (time.perf_counter() - t0):.2f}"
    return response


def svc(name: str):
    s = REGISTRY["services"].get(name)
    if s is None:
        raise HTTPException(503, f"service '{name}' unavailable: {REGISTRY['errors'].get(name, 'not loaded')}")
    return s


def _bad_request(fn, *args):
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(404, f"not found: {e}") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


# ---------------------------------------------------------------------------- health
@app.get("/health")
def health():
    return {"status": "ok" if REGISTRY["services"] else "degraded", "device": REGISTRY.get("device"),
            "loaded": sorted(REGISTRY["services"]), "errors": REGISTRY["errors"], "load_seconds": REGISTRY["load_seconds"]}


# ---------------------------------------------------------------------------- session pipeline
@app.post("/v1/session/{session_id}/start", tags=["session"])
def session_start(session_id: str, body: SessionStart):
    return _bad_request(svc("session").start, session_id, body.user.model_dump(), body.start_time, body.consent)


@app.post("/v1/session/{session_id}/events", tags=["session"])
def session_event(session_id: str, body: SessionEvent):
    """Score one raw event. PAYMENT_ATTEMPT events also return the alert decision."""
    return _bad_request(svc("session").add_event, session_id, body.model_dump(exclude_none=True))


@app.get("/v1/session/{session_id}", tags=["session"])
def session_summary(session_id: str):
    return _bad_request(svc("session").summary, session_id)


@app.post("/v1/demo/{typology}", tags=["session"])
def demo(typology: str, persona: str = "senior"):
    """Replay a deterministic simulator session (e.g. digital_arrest, family_transfer) through the pipeline, for one of
    the demo customers: senior (default), student or professional."""
    try:
        events, sessions, users, _ = generate_demo(typology, persona=persona)
    except KeyError as e:
        raise HTTPException(404, f"unknown typology or persona: {e}") from e
    s = svc("session")
    sid = f"demo-{typology}-{time.time_ns()}"
    user = users.set_index("user_id").loc[sessions["user_id"].iloc[0]].to_dict()
    s.start(sid, {"user_id": sessions["user_id"].iloc[0], **user}, sessions["start_time"].iloc[0])
    keep = set(SessionEvent.model_fields)
    timeline = []
    for _, r in events.iterrows():
        ev = {k: (None if pd.isna(v) else v) for k, v in r.items() if k in keep}
        if r.get("bio_ref") is not None and not pd.isna(r.get("bio_ref")) and s.bio_bank is not None:
            ev["gestures"] = s.bio_bank.resolve(r["bio_ref"])[1]  # the client sends the real gestures it captured
        ev = SessionEvent(**{k: v for k, v in ev.items() if v is not None}).model_dump(exclude_none=True)
        out = s.add_event(sid, ev)
        shown = {k: v for k, v in ev.items() if k != "gestures"}
        if "gestures" in ev:
            shown["gestures_n"] = len(ev["gestures"])
        timeline.append({"ts_min": round(r["ts"] / 60, 2), "true_stage": r["stage"], "input": shown, **out})
    return {"session_id": sid, "typology": typology, "persona": persona, "is_scam": bool(sessions["is_scam"].iloc[0]),
            "start_time": pd.Timestamp(sessions["start_time"].iloc[0]).isoformat(),
            "user": {"avg_txn_amount": round(float(user["avg_txn_amount"]), 2), "age_group": user.get("age_group")},
            "extraction_ts_min": None if sessions["extraction_ts"].isna().iloc[0] else round(sessions["extraction_ts"].iloc[0] / 60, 2),
            "timeline": timeline}


# ---------------------------------------------------------------------------- privacy: consent and telecom PSI
@app.post("/v1/consent/check", tags=["privacy"])
def consent_check(body: ConsentCheck):
    """Is this signal allowed for this customer right now? (DPDP purpose gate; every check is audited)."""
    reg = svc("session").consent
    return {"principal": body.principal, "purpose": body.purpose, "allowed": reg.check(body.principal, body.purpose, "api"),
            "audit_entries": len(reg.audit)}


@app.post("/v1/telecom/psi/demo", tags=["privacy"])
def telecom_psi_demo(body: PSIDemo):
    """Run a full DH private set intersection between the bank's numbers and the demo telecom's reported list."""
    from infra.privacy.psi import run_psi
    s = svc("session")
    t0 = time.perf_counter()
    r = run_psi(body.bank_numbers, sorted(s.telecom._party.items))
    return {"matches": r.matches, "bank_size": r.bank_size, "telecom_size": r.telecom_size, "messages": r.messages,
            "seconds": round(time.perf_counter() - t0, 2),
            "note": "the bank learns only which of its own numbers are reported; the telecom learns only the query size"}


@app.get("/v1/demo/touch", tags=["privacy"])
def demo_touch(profile: str = "normal", n: int = 10):
    """Demo/builder helper: a real HMOG touch window for the builder's demo customer (held-out subject).
    profile: normal (own hands) | coerced (own hands, modelled stress) | remote (someone else's hands)."""
    s = svc("session")
    if s.bio_bank is None:
        raise HTTPException(503, "HMOG gesture cache not available")
    if profile not in ("normal", "coerced", "rushed", "remote"):
        raise HTTPException(422, "profile must be normal, coerced, rushed or remote")
    from ml.sim.hmog_bank import seeded_rng
    subject = s.bio_bank.subjects[0]
    ref = s.bio_bank.window_ref(subject, profile, 1.0, seeded_rng("builder", profile, time.time_ns()))
    return {"subject": subject, "profile": profile, "gestures": s.bio_bank.resolve(ref)[1][:max(10, min(n, 20))]}


@app.get("/v1/demo/numbers", tags=["privacy"])
def demo_numbers():
    """Demo/builder helper: a few numbers on the demo telecom's reported list and a few that are not."""
    from ml.sim import telecom
    rep, clean = [], []
    for k in range(telecom.NUMBERS_PER_SYNDICATE):
        n, r = telecom.syndicate_number(0, k, False)
        (rep if r else clean).append(n)
    return {"reported": rep[:3], "clean": [telecom.genuine_number(k, False)[0] for k in range(3)]}


# ---------------------------------------------------------------------------- payee side: campaigns and cases
@app.post("/v1/payee/score", tags=["campaign"])
def payee_score(body: PayeeQuery):
    """How risky is this payee for this amount, from what the receiving side has seen (read-only; no state is created)."""
    return svc("campaign").payee_risk(body.payee_id, body.amount, body.payer_id, body.ts, body.payee_age_days, body.payee_is_merchant)


@app.post("/v1/campaign/ingest", tags=["campaign"])
def campaign_ingest(body: LedgerTransfer):
    """Feed one completed transfer into the payee-side state (what the beneficiary bank / switch sees)."""
    return svc("campaign").ingest(body.ts, body.src, body.dst, body.amount, body.src_bank, body.src_is_account,
                                  body.dst_age_days, body.dst_is_merchant)


@app.post("/v1/campaign/demo/load", tags=["campaign"])
def campaign_demo(body: DemoLoad):
    """Replay the synthetic ledger up to `until_day` (call again with a later day to advance it like a live feed)."""
    return svc("campaign").load_demo(body.n_sessions, 7, body.ambient_scale, body.until_day)


@app.get("/v1/campaign/cases", tags=["campaign"])
def campaign_cases(top: int = 10):
    """Campaign cases ranked by what an analyst can still save, each with an EN/HI summary and recommended actions."""
    c = svc("campaign")
    return {"summary": c.summary(), "cases": c.cases(max(1, min(top, 100)))}


@app.get("/v1/campaign/cases/{case_id}/graph", tags=["campaign"])
def campaign_case_graph(case_id: str, max_victims: int = 40, max_exits: int = 8):
    """Money flow of one case for the analyst graph: the case's accounts (with risk, balance and hop from the victims),
    the largest victim payments into them and the largest exits out of them, as aggregated edges."""
    return _bad_request(svc("campaign").case_graph, case_id, max(0, min(max_victims, 200)), max(0, min(max_exits, 50)))


@app.post("/v1/campaign/cases/{case_id}/hold", tags=["campaign"])
def campaign_hold(case_id: str, body: HoldRequest):
    """Analyst action: transaction-level credit hold on every account of the case. Never triggered automatically."""
    return _bad_request(svc("campaign").hold, case_id, body.analyst, body.reason)


@app.post("/v1/campaign/release", tags=["campaign"])
def campaign_release(accounts: list[str]):
    return svc("campaign").release(accounts)


# ---------------------------------------------------------------------------- component models
@app.post("/v1/gnn/score", tags=["gnn"])
def gnn_score(body: Transfer):
    """Laundering probability of an account-to-account transfer given both accounts' recent history."""
    r = body.model_dump()
    r["timestamp"] = r["timestamp"].isoformat()
    return _bad_request(svc("gnn").score, r, r.pop("record"))


@app.post("/v1/biometrics/enroll", tags=["biometrics"])
def bio_enroll(body: Gestures):
    return _bad_request(svc("biometrics").enroll, body.user_id, body.gestures)


@app.post("/v1/biometrics/verify", tags=["biometrics"])
def bio_verify(body: Gestures):
    """Similarity of the latest 10-20 gestures to the user's enrolled profile (BiLSTM + LDA fusion)."""
    return _bad_request(svc("biometrics").verify, body.user_id, body.gestures)


@app.post("/v1/tabular/score", tags=["tabular"])
def tabular_score(body: TabularRequest):
    """IEEE-CIS transaction risk from engineered features (missing features allowed)."""
    return _bad_request(svc("tabular").score, body.transactions)


@app.post("/v1/admin/reset", tags=["admin"])
def reset(services: str = "campaign,session,gnn"):
    """Clear in-memory state: payee-side ledger and cases (campaign), sessions and alert-policy history (session),
    the GNN's online transfer buffer (gnn). `services` limits it, e.g. `?services=session`."""
    names = [s.strip() for s in services.split(",") if s.strip()]
    for name in names:
        if name in ("campaign", "session", "gnn") and name in REGISTRY["services"]:
            REGISTRY["services"][name].reset()
    return {"reset": names}
