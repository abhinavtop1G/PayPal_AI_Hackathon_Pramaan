"""The authentication service object behind POST /v1/authenticate and POST /v1/challenge/verify.

    request -> touch score (BiLSTM + LDA, if gestures and an enrolled profile) -> typing score (1D-CNN, if keystrokes
    and an enrolled profile) -> payee risk (payee intelligence, if
    the receiving account is known) -> features (request + live state) -> risk model -> policy -> decision + signals

State changes: every attempt is recorded against its device and IP; an allowed payment, or one whose challenge
passes, is committed to the user's history; a passed strong challenge (passkey, bank call-back) makes the device
trusted; a failed challenge is recorded and blocks the next attempts for 30 minutes.
"""
from __future__ import annotations

import time
import uuid

import numpy as np

from .features import FEATURES, REASON, build
from .model import AuthModel
from .policy import AuthPolicy, message
from .state import AuthState

STRONG_CHALLENGES = {"passkey", "bank_callback"}


class AuthEngine:
    def __init__(self, model: AuthModel, policy: AuthPolicy | None = None, state: AuthState | None = None,
                 bio=None, payee=None, audit=None, reason_min: float = 0.15, typing=None):
        self.model = model
        self.policy = policy or AuthPolicy()
        self.state = state or AuthState()
        self.bio = bio          # ml.models.biometrics.scorer.BioScorer (optional)
        self.payee = payee      # backend.campaign_service.CampaignService (optional)
        self.typing = typing    # ml.models.keystroke.scorer.KeystrokeScorer (optional)
        self.audit = audit      # callable(record: dict) (optional)
        self.reason_min = reason_min

    # ------------------------------------------------------------------ enrichment
    def _enrich(self, req: dict, timings: dict | None = None) -> dict:
        timings = {} if timings is None else timings
        t = time.perf_counter()
        beh = req.setdefault("behaviour", {})
        gestures = beh.pop("gestures", None)
        if beh.get("bio_dev") is None and gestures and self.bio is not None and req["user_id"] in self.bio.profiles:
            if len(gestures) >= 10:
                beh["bio_dev"] = float(self.bio.verify(req["user_id"], gestures)["behavioural_deviation"])
        timings["touch"], t = 1000 * (time.perf_counter() - t), time.perf_counter()
        keys = beh.pop("keystrokes", None)
        if beh.get("typing_dev") is None and keys and self.typing is not None and req["user_id"] in self.typing.profiles:
            beh["typing_dev"] = float(self.typing.verify(req["user_id"], keys)["typing_deviation"])
        timings["typing"], t = 1000 * (time.perf_counter() - t), time.perf_counter()
        tx = req.setdefault("transaction", {})
        if tx.get("payee_risk") is None and tx.get("payee_id") and self.payee is not None and (tx.get("amount") or 0) > 0:
            try:
                r = self.payee.payee_risk(tx["payee_id"], float(tx["amount"]), req["user_id"])
                if r.get("known_account"):
                    tx["payee_risk"] = max(r["risk"], 0.9 if r.get("held") else 0.0)
                    tx["payee_case_id"] = r.get("case_id")
            except Exception:  # payee intelligence is optional; never fail the decision because of it
                pass
        timings["payee"] = 1000 * (time.perf_counter() - t)
        return req

    # ------------------------------------------------------------------ decisions
    def authenticate(self, req: dict, explain: bool = True) -> dict:
        t0 = time.perf_counter()
        timings: dict[str, float] = {}
        req = self._enrich(req, timings)
        t = time.perf_counter()
        now, uid = float(req["ts"]), req["user_id"]
        f, ctx = build(req, self.state)
        amount = float((req.get("transaction") or {}).get("amount") or 0)
        timings["features"], t = 1000 * (time.perf_counter() - t), time.perf_counter()
        if explain:
            p, signals, fam = self.model.explain(f)
        else:
            x = np.array([[f.get(k, np.nan) for k in self.model.features]], dtype="float32")
            m = self.model.booster.inplace_predict(x, predict_type="margin",
                                                   iteration_range=(0, self.model.best_iteration + 1))
            p, signals, fam = float(1 / (1 + np.exp(-(m[0] + self.model.shift)))), [], {}
        timings["model"], t = 1000 * (time.perf_counter() - t), time.perf_counter()
        d = self.policy.decide(p, amount, f, ctx)
        timings["policy"] = 1000 * (time.perf_counter() - t)
        # log-odds before any signal (bias + prior correction): base_logit + sum of contributions = logit(risk)
        pc = min(max(p, 1e-12), 1 - 1e-12)
        base_logit = float(np.log(pc / (1 - pc)) - sum(s["contribution"] for s in signals)) if signals else None
        dev, net = req.get("device") or {}, req.get("network") or {}
        self.state.record_attempt(uid, dev.get("device_id"), net.get("ip"), now)
        decision_id = req.get("request_id") or uuid.uuid4().hex[:16]
        if d["decision"] == "allow":
            self.state.commit(uid, req, now)
        elif d["decision"] == "challenge":
            self.state.put_pending(decision_id, {"req": _slim(req), "challenge_type": d["challenge_type"], "p": p})
        coached = bool(f.get("unknown_call_active") or f.get("screen_share_active")) and ctx.get("device_trusted")
        en, hi = message(d["decision"], d["challenge_type"], coached)
        # reasons explain an interruption; an allowed payment has none (small positive contributions are noise there)
        reasons = [] if d["decision"] == "allow" else [
            {"signal": s["name"], "family": s["family"], "text_en": REASON[s["name"]][0], "text_hi": REASON[s["name"]][1],
             "contribution": s["contribution"]} for s in signals if s["contribution"] >= self.reason_min][:3]
        out = {"decision_id": decision_id, "user_id": uid, "decision": d["decision"], "risk_score": round(p, 5),
               "challenge_type": d["challenge_type"], "rule": d["rule"], "message_en": en, "message_hi": hi,
               "reasons": reasons, "family_contribution": fam, "signals": signals,
               "features": {k: (None if not np.isfinite(v) else round(float(v), 4)) for k, v in f.items()},
               "expected_cost": d["expected_cost"], "amount": amount,
               "model_version": getattr(self.model, "meta", {}).get("version", "dev"),
               "base_logit": None if base_logit is None else round(base_logit, 4),
               "timings_ms": {k: round(v, 3) for k, v in timings.items()},
               "latency_ms": round(1000 * (time.perf_counter() - t0), 2)}
        if self.audit is not None:
            self.audit({"kind": "decision", "ts": now, **{k: out[k] for k in ("decision_id", "user_id", "decision",
                        "risk_score", "challenge_type", "rule", "amount", "latency_ms")},
                        "reasons": [r["signal"] for r in reasons]})
        return out

    def verify_challenge(self, decision_id: str, passed: bool, now: float | None = None) -> dict:
        doc = self.state.pop_pending(decision_id)
        if doc is None:
            raise KeyError(f"no pending challenge {decision_id} (unknown or expired)")
        req = doc["req"]
        now = float(now if now is not None else req["ts"])
        uid, dev_id = req["user_id"], (req.get("device") or {}).get("device_id")
        if passed:
            self.state.commit(uid, req, now, trust_device=doc["challenge_type"] in STRONG_CHALLENGES)
            final = "allow"
        else:
            self.state.record_failure(uid, now)
            final = "block"
        en, hi = message(final, None)
        out = {"decision_id": decision_id, "user_id": uid, "challenge_type": doc["challenge_type"], "passed": bool(passed),
               "decision": final, "device_trusted": bool(passed and doc["challenge_type"] in STRONG_CHALLENGES and dev_id),
               "message_en": en, "message_hi": hi}
        if self.audit is not None:
            self.audit({"kind": "challenge", "ts": now, "decision_id": decision_id, "user_id": uid,
                        "decision": final, "challenge_type": doc["challenge_type"], "passed": bool(passed)})
        return out


def _slim(req: dict) -> dict:
    """What a pending challenge needs to commit the transaction later (no gestures)."""
    keep = {k: req.get(k) for k in ("user_id", "ts", "channel", "event_type")}
    for part in ("device", "network", "transaction"):
        keep[part] = dict(req.get(part) or {})
    return keep


__all__ = ["AuthEngine", "FEATURES"]
