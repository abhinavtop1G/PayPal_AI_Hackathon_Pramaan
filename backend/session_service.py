"""Stateful session pipeline: raw events -> context -> workflow GRU -> (at payment attempts) fusion + policy.

Every event returns the GRU's live view (P(scam in progress), stage, likely typology). PAYMENT_ATTEMPT
events additionally return the engine decision (action, reasons, EN/HI message). The payee score
used by fusion is `payee_mule_score` from the event — the slot the GNN's account score fills.
"""
import os
import threading
import time

import numpy as np
import pandas as pd

from ml.engine.components import component_table, gru_outputs, load_gru
from ml.engine.fusion import FusionModel
from ml.engine.messages import render
from ml.engine.policy import AlertPolicy
from ml.models.workflow.data import BIO, STAGES, TYPOLOGIES, SeqData, featurise
from ml.sim.schema import EVENT_COLUMNS, Ev

from infra.privacy.consent import PURPOSES, ConsentRegistry
from infra.privacy.reputation import ReputationClient, Telecom
from ml.sim.telecom import reported_numbers

from .campaign_service import campaign_override, to_seconds
from .context import ContextTracker

N_SYNDICATES = 12  # ml.sim.entities.World default


def _load_bio(device: str):
    """The real HMOG scorer and gesture bank, or (None, None) when the artifacts / HMOG cache are missing."""
    try:
        from ml.models.biometrics.scorer import BioScorer
        from ml.sim.hmog_bank import HmogBank
        return BioScorer(device), HmogBank.load()
    except Exception:  # noqa: BLE001  (serve without biometrics rather than fail)
        return None, None

FUSION_DIR = os.environ.get("RAKSHAM_FUSION_DIR", "ml/engine/artifacts")
DEFAULT_BIO = {"pressure": 0.52, "swipe_velocity": 1.0, "tap_interval_ms": 480.0, "hesitation_ms": 1800.0,
               "orientation_var": 0.05}  # population-typical baselines when a profile has none
CONTEXT_COLS = ["call_active", "caller_kind", "call_video", "call_elapsed_s", "caller_number", "caller_reported",
                "screen_share_active", "sideloaded_app_present", "accessibility_granted"]
SERVER_COLS = ["bio_model_dev", "bio_ref"]  # computed here, never taken from the client


PAYEE_EVENTS = {Ev.PAYEE_ADD.value, Ev.PAYMENT_ATTEMPT.value, Ev.PAYMENT_SUCCESS.value}


class SessionService:
    def __init__(self, device: str = "cuda", campaign=None):
        self.device = device
        self.campaign = campaign  # payee-side CampaignService; fills in `payee_mule_score` when the client sends none
        self.consent = ConsentRegistry()
        # telecom side of the PSI: the demo telecom's list of numbers reported to 1930 (simulator syndicates + false reports)
        self.telecom = Telecom(reported_numbers(N_SYNDICATES))
        self.reputation = ReputationClient(self.telecom, background=True)
        self.bio, self.bio_bank = _load_bio(device)
        self.gru = load_gru(device)
        self.fusion = FusionModel.load(FUSION_DIR)
        self.policy = AlertPolicy()
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()
        self._warmup()

    def _warmup(self) -> None:
        """Run one tiny session so the first real request doesn't pay CUDA/cuDNN initialisation."""
        self.start("_warmup", {"user_id": "_warmup", "avg_txn_amount": 1000.0}, pd.Timestamp("2026-01-01"))
        self.add_event("_warmup", {"event": "CALL_START", "ts": 0.0, "caller_kind": "unknown"})
        self.add_event("_warmup", {"event": "PAYMENT_ATTEMPT", "ts": 60.0, "amount": 5000.0, "payee_id": "x",
                                   "payee_is_new": True, "payee_is_merchant": False, "payee_vpa_age_days": 10.0,
                                   "payee_mule_score": 0.5})
        self.reset()

    # ---------------------------------------------------------------- lifecycle
    def start(self, session_id: str, user: dict, start_time: pd.Timestamp, consent: list[str] | None = None) -> dict:
        profile = {"user_id": user["user_id"], "avg_txn_amount": float(user["avg_txn_amount"])}
        for k in BIO:
            profile[f"bio_{k}_baseline"] = float(user.get(f"bio_{k}_baseline") or DEFAULT_BIO[k])
        art = self.consent.grant(user["user_id"], PURPOSES if consent is None else consent)
        # touch profile: demo customers enrol from their held-out HMOG subject (real clients: /v1/biometrics/enroll)
        bio_key = None
        subj = user.get("hmog_subject")
        if self.bio is not None and subj is not None and not pd.isna(subj):
            bio_key = f"hmog:{int(subj)}"
            if bio_key not in self.bio.profiles:
                self.bio.enroll(bio_key, self.bio_bank.enrolment(int(subj)))
        elif self.bio is not None and user["user_id"] in self.bio.profiles:
            bio_key = user["user_id"]
        uid = user["user_id"]
        ctx = ContextTracker(lookup=lambda n: (self.reputation.is_reported(n)
                                               if self.consent.check(uid, "telecom_reputation") else None))
        with self.lock:
            self.sessions[session_id] = {"user": profile, "start_time": pd.Timestamp(start_time), "rows": [],
                                         "ctx": ctx, "decisions": [], "bio_key": bio_key}
        return {"session_id": session_id, "started": True, "consent_id": art.consent_id,
                "purposes": sorted(art.purposes), "touch_profile": bio_key is not None}

    def reset(self) -> None:
        with self.lock:
            self.sessions.clear()
            self.policy = AlertPolicy()

    # ---------------------------------------------------------------- scoring
    def add_event(self, session_id: str, ev: dict) -> dict:
        t0 = time.perf_counter()
        with self.lock:
            s = self.sessions.get(session_id)
            if s is None:
                raise KeyError(session_id)
            if s["rows"] and float(ev["ts"]) < s["rows"][-1]["ts"]:
                raise ValueError("events must arrive in time order (ts is seconds since session start)")
            row = dict.fromkeys(EVENT_COLUMNS)
            row.update({k: v for k, v in ev.items() if k in EVENT_COLUMNS and k not in CONTEXT_COLS and k not in SERVER_COLS})
            bio_signal = self._touch(s, ev)
            if bio_signal is not None:
                row["bio_model_dev"] = bio_signal["behavioural_deviation"]
            row.update(session_id=session_id, user_id=s["user"]["user_id"], stage=STAGES[0],
                       event_time=s["start_time"] + pd.Timedelta(seconds=float(ev["ts"])))
            row.update(s["ctx"].snapshot(ev))
            payee = self._payee(s, row)
            s["rows"].append(row)
            out = self._score(session_id, s, payee)
        out["signals"] = {"caller_reported": row.get("caller_reported"), "touch": bio_signal}
        out["latency_ms"] = round(1000 * (time.perf_counter() - t0), 2)
        return out

    def _touch(self, s: dict, ev: dict) -> dict | None:
        """Real biometrics on a BIO_WINDOW that carries gestures, if the customer has a touch profile and consented."""
        if ev.get("event") != Ev.BIO_WINDOW.value or not ev.get("gestures") or self.bio is None or not s.get("bio_key"):
            return None
        if not self.consent.check(s["user"]["user_id"], "behavioural_biometrics"):
            return None
        r = self.bio.verify(s["bio_key"], ev["gestures"])
        return {"behavioural_deviation": r["behavioural_deviation"], "matches_profile": bool(r["matches_profile"]),
                "fused_score": r["fused_score"]}

    def _payee(self, s: dict, row: dict) -> dict | None:
        """Payee-side intelligence for a payment-related event. A client-supplied `payee_mule_score` wins; otherwise the
        campaign service scores the payee and the result is written into the row, which is what the GRU reads."""
        if row["event"] not in PAYEE_EVENTS or not row.get("payee_id"):
            return None
        if row.get("payee_mule_score") is not None and not pd.isna(row["payee_mule_score"]):
            return {"source": "client", "risk": float(row["payee_mule_score"])}
        if self.campaign is None:
            return None
        now = s["start_time"] + pd.Timedelta(seconds=float(row["ts"]))
        info = self.campaign.payee_risk(row["payee_id"], float(row.get("amount") or 1.0), s["user"]["user_id"], to_seconds(now),
                                        row.get("payee_vpa_age_days"), row.get("payee_is_merchant"))
        row["payee_mule_score"] = info["risk"]
        return {"source": "campaign", **info}

    def _seqdata(self, session_id: str, s: dict) -> SeqData:
        events = pd.DataFrame(s["rows"], columns=EVENT_COLUMNS)
        for c in ["call_active", "call_video", "screen_share_active", "sideloaded_app_present", "accessibility_granted",
                  "sms_has_link", "payee_is_merchant", "payee_is_new"]:
            events[c] = events[c].astype("boolean")
        for c in ["ts", "call_elapsed_s", "payee_vpa_age_days", "payee_mule_score", "amount"] + [f"bio_{k}" for k in BIO]:
            events[c] = pd.to_numeric(events[c], errors="coerce").astype("float64")
        num, cat = featurise(events, pd.DataFrame([s["user"]]))
        n = len(events)
        sess = pd.DataFrame({"session_id": [session_id], "user_id": [s["user"]["user_id"]], "start_time": [s["start_time"]],
                             "is_scam": [False], "typology": ["unknown"], "extraction_ts": [np.nan], "typology_id": [0]})
        return SeqData(num=[num.to_numpy()], cat=[cat], stage=[np.zeros(n, "int64")],
                       is_payment=[(events["event"] == Ev.PAYMENT_ATTEMPT.value).to_numpy()],
                       ts=[events["ts"].to_numpy("float64")], amount=[events["amount"].fillna(0).to_numpy("float64")],
                       sessions=sess, num_names=list(num.columns))

    def _score(self, session_id: str, s: dict, payee: dict | None = None) -> dict:
        d = self._seqdata(session_id, s)
        p, stage, typ = gru_outputs(self.gru, d, self.device)[0]
        j = len(s["rows"]) - 1
        top = np.argsort(typ[j])[::-1][:3]
        out = {"event_index": j, "event": s["rows"][j]["event"],
               "workflow": {"p_scam_in_progress": round(float(p[j]), 5), "stage": STAGES[int(stage[j])],
                            "typology_top3": {TYPOLOGIES[k]: round(float(typ[j, k]), 4) for k in top}},
               "decision": None}
        if s["rows"][j]["event"] == Ev.PAYMENT_ATTEMPT.value:
            comp = component_table(d, [(p, stage, typ)])
            row = comp[comp["event_idx"] == j].iloc[0]
            prob = float(self.fusion.proba(row.to_frame().T)[0])
            now = s["start_time"] + pd.Timedelta(seconds=float(row["ts"]))
            dec = self.policy.decide(row, prob, now, self.fusion.reasons(row.to_frame().T))
            floor, why = campaign_override(dec.action, prob, payee if payee and payee.get("source") == "campaign" else None,
                                           self.policy.monitor_p)
            if why:  # campaign evidence raises the floor; the session decision is otherwise untouched
                dec.action, dec.suppressed_by, dec.notify = floor, None, True
                dec.reasons = list(dec.reasons) + [why]
                dec.message_en, dec.message_hi = render(floor, None, dec.reasons)
            out["payee"] = payee
            out["decision"] = {"action": dec.action, "notify": dec.notify, "fused_risk": round(prob, 6),
                               "ev_choice": dec.ev_choice, "suppressed_by": dec.suppressed_by, "reasons": dec.reasons,
                               "message_en": dec.message_en, "message_hi": dec.message_hi,
                               "components": {k: round(float(row[k]), 4) for k in
                                              ("gru_p", "mule_score", "bio_dev", "log_amt_vs_avg", "payee_is_new", "caller_reported_active",
                                               "unknown_call_active", "payee_known_trusted")}}
            s["decisions"].append({"event_index": j, **out["decision"]})
        return out

    def summary(self, session_id: str) -> dict:
        s = self.sessions[session_id]
        return {"session_id": session_id, "n_events": len(s["rows"]), "decisions": s["decisions"]}
