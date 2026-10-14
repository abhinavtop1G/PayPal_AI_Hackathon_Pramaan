"""Alert policy: pick the action with the best expected value, then apply anti-fatigue rules.

Expected value of a tier at a payment attempt with fused risk p and amount A:
    EV(tier) = p * A * efficacy(tier) - (1 - p) * friction(tier)
efficacy = share of scams the action stops; friction = cost of interrupting a legitimate user
(annoyance, abandoned payments, support load), in rupee-equivalents. These are *assumptions*
to be tuned with the bank, not measured values.

Anti-fatigue rules (applied after the EV choice):
  1. escalate-only   - within a session, never repeat or lower an interruption. If the user goes ahead
                       after a warning and the next payment is still risky, escalate one tier instead
                       (ignoring a warning is itself a risk signal). Once a session is on hold, later
                       payments stay held without a new notification.
  2. trusted payee   - payees the user pays regularly (with clean payee intel) never get nudge/cool-off
  3. user budget     - at most `user_budget` nudge/cool-off interruptions per user per 30 days;
                       beyond that they are logged for the analyst instead. Hold is never suppressed.
Anything above `monitor_p` that isn't interrupted goes to a silent analyst queue ("monitor").
"""
from collections import defaultdict, deque
from dataclasses import dataclass, field

import pandas as pd

from .messages import render

SCAM_TYPS = {"digital_arrest", "fake_kyc_apk", "investment_task", "voice_clone_relative"}


@dataclass(frozen=True)
class Tier:
    name: str
    rank: int
    efficacy: float
    friction: float
    interruptive: bool


TIERS = [
    Tier("allow", 0, 0.0, 0.0, False),
    Tier("nudge", 1, 0.20, 10.0, True),     # in-app warning, user can continue
    Tier("cool_off", 2, 0.50, 60.0, True),  # payment paused for 10 minutes with scam-specific message
    Tier("hold", 3, 0.90, 250.0, True),     # payment held, bank calls back on registered number
]
BY_NAME = {t.name: t for t in TIERS}


@dataclass
class Decision:
    action: str
    p: float
    ev_choice: str
    suppressed_by: str | None = None
    reasons: list = field(default_factory=list)
    notify: bool = False  # True when this decision sends the user a new message (what fatigue is about)
    message_en: str = ""
    message_hi: str = ""


@dataclass
class AlertPolicy:
    tiers: list = field(default_factory=lambda: list(TIERS))
    user_budget: int = 2
    budget_window_days: float = 30.0
    monitor_p: float = 0.02
    anti_fatigue: bool = True

    def __post_init__(self):
        self._session_max = defaultdict(int)   # session_id -> highest tier rank issued
        self._user_hist = defaultdict(deque)   # user_id -> timestamps of nudge/cool-off interruptions

    def ev_choice(self, p: float, amount: float) -> Tier:
        return max(self.tiers, key=lambda t: p * amount * t.efficacy - (1 - p) * t.friction)

    def decide(self, row: pd.Series, p: float, now: pd.Timestamp, reasons=None) -> Decision:
        tier = self.ev_choice(p, row["amount"])
        d = Decision(action=tier.name, p=p, ev_choice=tier.name, reasons=[r for r, _ in (reasons or [])])
        sid, uid = row["session_id"], row["user_id"]
        if self.anti_fatigue and self._session_max[sid] == BY_NAME["hold"].rank:  # session already on hold: keep holding, no new message
            d.action, d.suppressed_by = "hold", "session_on_hold"
            return d
        if tier.interruptive and self.anti_fatigue:
            if tier.rank <= self._session_max[sid]:  # user went ahead after a warning: escalate one tier
                d.action, d.suppressed_by = self.tiers[self._session_max[sid] + 1].name, "escalated_on_repeat"
            elif tier.name != "hold" and row.get("payee_known_trusted", 0) > 0:
                d.action, d.suppressed_by = "allow", "trusted_payee"
            elif tier.name != "hold":
                hist = self._user_hist[uid]
                while hist and (now - hist[0]).total_seconds() > self.budget_window_days * 86400:
                    hist.popleft()
                if len(hist) >= self.user_budget:
                    d.action, d.suppressed_by = "allow", "user_budget"
        final = BY_NAME[d.action]
        if final.interruptive:
            d.notify = True
            self._session_max[row["session_id"]] = final.rank
            if final.name != "hold":
                self._user_hist[row["user_id"]].append(now)
            typ = row.get("pred_typology")
            conf = row.get(f"typ_{typ}", 0.0) if typ else 0.0
            d.message_en, d.message_hi = render(final.name, typ if typ in SCAM_TYPS and conf >= 0.5 else None, d.reasons)
        elif p >= self.monitor_p:
            d.action = "monitor"
        return d
