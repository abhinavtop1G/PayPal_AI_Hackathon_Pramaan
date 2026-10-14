"""Server-side session context from raw events (clients send only what happened).

Mirrors sim/builder.py snapshot semantics so served features match training features:
  * "start"-type events update state *before* the snapshot (CALL_START row shows the call active,
    APP_INSTALL from a sideload shows sideloaded, ACCESSIBILITY_GRANT shows granted, SCREEN_SHARE_START shows sharing)
  * "end"-type events update state *after* the snapshot (CALL_END / SCREEN_SHARE_END rows still show it active)
"""
from dataclasses import dataclass

from ml.sim.schema import Ev


@dataclass
class ContextTracker:
    call_active: bool = False
    caller_kind: str | None = None
    caller_number: str | None = None
    caller_reported: bool | None = None
    # number -> reported?  (telecom PSI behind the consent gate); None = no lookup available / not consented
    lookup: object = None
    call_video: bool | None = None
    call_start_ts: float | None = None
    screen_share: bool = False
    sideloaded: bool = False
    accessibility: bool = False

    def snapshot(self, ev: dict) -> dict:
        """Apply `ev` and return the context columns for its row."""
        e, ts = ev["event"], float(ev["ts"])
        if e == Ev.CALL_START.value:
            self.call_active, self.caller_kind = True, ev.get("caller_kind") or "unknown"
            self.call_video, self.call_start_ts = bool(ev.get("call_video") or False), ts
            self.caller_number = ev.get("caller_number")
            self.caller_reported = self.lookup(self.caller_number) if (self.lookup and self.caller_number) else None
        elif e == Ev.APP_INSTALL.value and ev.get("app_source") == "sideload":
            self.sideloaded = True
        elif e == Ev.ACCESSIBILITY_GRANT.value:
            self.accessibility = True
        elif e == Ev.SCREEN_SHARE_START.value:
            self.screen_share = True
        snap = {
            "call_active": self.call_active, "caller_kind": self.caller_kind, "call_video": self.call_video,
            "call_elapsed_s": round(ts - self.call_start_ts, 2) if self.call_active else None,
            "caller_number": self.caller_number, "caller_reported": self.caller_reported,
            "screen_share_active": self.screen_share, "sideloaded_app_present": self.sideloaded,
            "accessibility_granted": self.accessibility,
        }
        if e == Ev.CALL_END.value:
            self.call_active, self.caller_kind, self.call_video, self.call_start_ts = False, None, None, None
            self.caller_number = self.caller_reported = None
        elif e == Ev.SCREEN_SHARE_END.value:
            self.screen_share = False
        return snap
