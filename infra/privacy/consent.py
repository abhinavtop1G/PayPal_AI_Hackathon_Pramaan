"""DPDP-style consent artefacts and a purpose gate.

Under the Digital Personal Data Protection Act 2023 a bank may process personal data for a specified purpose the data
principal consented to (or a "legitimate use"). RAKSHAM's session pipeline uses three kinds of data, each tied to a
purpose; a signal is used only if the session's consent artefact covers its purpose and has not expired:

    fraud_prevention        session events and payment details (the core pipeline)
    telecom_reputation      the caller's number, checked against telecom-reported numbers via PSI
    behavioural_biometrics  touch gestures, scored against the customer's enrolled profile

Every check is appended to an audit log (who asked, for which purpose, allowed or not) so the bank can show the
regulator why a signal was or was not used. This models the shape of a consent manager, not a full implementation.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

PURPOSES = ("fraud_prevention", "telecom_reputation", "behavioural_biometrics")


@dataclass(frozen=True)
class ConsentArtefact:
    principal: str                       # the customer (pseudonymous id)
    purposes: frozenset[str]
    fiduciary: str = "raksham-demo-bank"
    issued_at: float = field(default_factory=time.time)
    expires_at: float | None = None      # None: until revoked
    consent_id: str = field(default_factory=lambda: f"CA-{uuid.uuid4().hex[:12]}")

    def __post_init__(self):
        unknown = set(self.purposes) - set(PURPOSES)
        if unknown:
            raise ValueError(f"unknown purpose(s): {sorted(unknown)}")

    def allows(self, purpose: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return purpose in self.purposes and (self.expires_at is None or now < self.expires_at)


class ConsentRegistry:
    """Grant, revoke and check consent; every check is audited."""

    def __init__(self):
        self._by_principal: dict[str, ConsentArtefact] = {}
        self.audit: list[dict] = []

    def grant(self, principal: str, purposes, ttl_s: float | None = None, now: float | None = None) -> ConsentArtefact:
        now = time.time() if now is None else now
        a = ConsentArtefact(principal, frozenset(purposes), issued_at=now, expires_at=None if ttl_s is None else now + ttl_s)
        self._by_principal[principal] = a
        return a

    def revoke(self, principal: str) -> bool:
        return self._by_principal.pop(principal, None) is not None

    def get(self, principal: str) -> ConsentArtefact | None:
        return self._by_principal.get(principal)

    def check(self, principal: str, purpose: str, requester: str = "session-pipeline", now: float | None = None) -> bool:
        a = self._by_principal.get(principal)
        ok = bool(a and a.allows(purpose, now))
        self.audit.append({"t": time.time() if now is None else now, "principal": principal, "purpose": purpose,
                           "requester": requester, "allowed": ok, "consent_id": a.consent_id if a else None})
        return ok
