"""Transaction-authentication service for the API: the AuthEngine (ml/auth) with live state, the audit log, the
touch-biometrics scorer and payee intelligence when those services are loaded, and the demo customer.

State backend: Redis when REDIS_URL is set (shared by every Cloud Run instance), otherwise in-process memory.
"""
from __future__ import annotations

import time

import numpy as np

from ml.auth.demo import SCENARIOS, USER, DemoWorld
from ml.auth.engine import AuthEngine
from ml.auth.model import AuthModel
from ml.auth.policy import AuthPolicy
from ml.auth.state import AuthState, make_kv

from .audit import AuditLog


class AuthService:
    def __init__(self, bio=None, payee=None, typing=None):
        self.model = AuthModel.load()
        self.state = AuthState(make_kv())
        self.audit = AuditLog()
        self.bio, self.typing = bio, typing
        self.engine = AuthEngine(self.model, AuthPolicy(), self.state, bio=bio, payee=payee, audit=self.audit, typing=typing)
        self.demo = DemoWorld()
        self.demo.seed(self.state, bio, typer=typing)
        self._warm_up()

    def _warm_up(self):
        """One unaudited decision at startup, so the first real request does not pay for lazy initialisation
        (torch kernels, XGBoost's SHAP path); the demo customer's history is reset afterwards."""
        audit, self.engine.audit = self.engine.audit, None
        try:
            self.run_demo("genuine_routine")
        except Exception:  # warming up is best effort: never keep the service from starting
            pass
        finally:
            self.engine.audit = audit
            self.demo.seed(self.state, self.bio, typer=self.typing)

    def info(self) -> dict:
        return {"model_version": self.model.meta.get("version"), "features": len(self.model.features),
                "real_prior": self.model.real_prior, "state_backend": self.state.kv.backend,
                "audit_backend": self.audit.backend, "touch_biometrics": self.bio is not None,
                "payee_intelligence": self.engine.payee is not None, "typing_biometrics": self.typing is not None,
                "demo_gestures": self.demo.pack is not None, "demo_keystrokes": self.demo.kpack is not None}

    def authenticate(self, req: dict) -> dict:
        if req.get("ts") is None:
            req["ts"] = time.time()
        return self.engine.authenticate(req)

    def verify(self, decision_id: str, passed: bool) -> dict:
        return self.engine.verify_challenge(decision_id, passed, time.time())

    def verify_demo(self, decision_id: str, passed: bool) -> dict:
        doc = self.state.kv.get(f"pending:{decision_id}")
        if doc is None or doc["req"]["user_id"] != USER:
            raise KeyError(f"no pending demo challenge {decision_id}")
        return self.verify(decision_id, passed)

    # ------------------------------------------------------------------ demo
    def run_demo(self, scenario: str, overrides: dict | None = None) -> dict:
        now = time.time()
        self.demo.seed(self.state, self.bio, now - 1, typer=self.typing)  # every scenario starts from the same history
        req = self.demo.request("genuine_routine" if scenario == "custom" else scenario, now)
        for part, vals in (overrides or {}).items():
            if isinstance(vals, dict) and isinstance(req.get(part), dict):
                req[part].update(vals)
            else:
                req[part] = vals
        typing = req["behaviour"].pop("typing_profile", None)  # console: her typing / someone else's / scripted / none
        if typing == "none":
            req["behaviour"]["keystrokes"] = None
        elif typing in ("normal", "remote", "bot", "coerced"):
            req["behaviour"]["keystrokes"] = self.demo.keystrokes(typing, np.random.default_rng())
        profile = req["behaviour"].pop("touch_profile", None)  # console: own / stressed / someone else's hands / none
        if profile == "none":
            req["behaviour"]["gestures"] = None
        elif profile in ("normal", "coerced", "remote"):
            req["behaviour"]["gestures"] = self.demo.gestures(profile, np.random.default_rng())
        self.demo.prepare(scenario, self.state, now)
        shown = {k: (dict(v) if isinstance(v, dict) else v) for k, v in req.items()}
        if shown["behaviour"].get("gestures"):
            shown["behaviour"]["gestures"] = f"{len(shown['behaviour']['gestures'])} real HMOG touch gestures"
        if shown["behaviour"].get("keystrokes"):
            shown["behaviour"]["keystrokes"] = "1 password attempt (31 key timings, CMU)"
        title, story, is_attack = SCENARIOS.get(scenario, ("Custom request", "Built in the console.", None))
        return {"scenario": scenario, "title": title, "story": story, "is_attack": is_attack, "request": shown,
                "response": self.engine.authenticate(req)}

    def reset(self):
        self.state.kv.clear()
        self.demo.seed(self.state, self.bio, typer=self.typing)


def scenario_list() -> list[dict]:
    return [{"id": k, "title": t, "story": s, "is_attack": a} for k, (t, s, a) in SCENARIOS.items()] + [
        {"id": "custom", "title": "Custom", "story": f"Build any request for the demo customer ({USER}).", "is_attack": None}]
