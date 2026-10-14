"""SessionBuilder: stateful helper that typology scripts drive to emit event rows.

It tracks session context (active call, screen share, sideloaded app, accessibility grant) and
snapshots it onto every row, so downstream models see "paying a new payee *while* on a 40-minute
VoIP video call" without having to reconstruct state themselves.
"""
import numpy as np

from . import telecom
from .entities import User, World
from .hmog_bank import seeded_rng
from .schema import EVENT_COLUMNS, Ev, Stage

# Adaptive-scammer knobs (ml/engine/robustness.py). Each applies to scam sessions only:
#   no_call        calls happen on an OTT app the bank cannot see (no CALL_START/CALL_END, no caller context)
#   slow           every wait is 5x longer (the workflow is stretched over hours or days)
#   split_amounts  each payment is split into 3-5 smaller ones
#   clean_device   no sideloaded app, no screen control or screen share (store installs only)
#   calm_hands     touch behaviour stays normal (no coerced / rushed / remote signal)
#   fresh_numbers  every call comes from a never-reported number
ADVERSARY_KNOBS = ("no_call", "slow", "split_amounts", "clean_device", "calm_hands", "fresh_numbers")

# Multiplicative factors on the user's own baseline: (pressure, swipe_velocity, tap_interval, hesitation, orientation_var)
BIO_PROFILES = {
    "normal":     (1.00, 1.00, 1.00, 1.00, 1.0),
    "distracted": (1.05, 0.95, 1.15, 1.40, 1.6),  # benign: paying while talking on the phone
    "coerced":    (1.35, 0.80, 1.40, 3.00, 2.2),  # fear / being instructed step by step
    "rushed":     (1.20, 1.30, 0.70, 0.45, 1.5),  # urgency: "send now, I'm in trouble"
}
# Remote-access / overlay malware injects synthetic touches: flat pressure, metronomic taps, phone lying still.
REMOTE_ABS = {"pressure": 0.50, "swipe_velocity": 2.5, "tap_interval_ms": 120.0, "hesitation_ms": 150.0, "orientation_var": 0.002}
BIO_KEYS = ["pressure", "swipe_velocity", "tap_interval_ms", "hesitation_ms", "orientation_var"]


class SessionBuilder:
    def __init__(self, session_id: str, user: User, world: World, rng: np.random.Generator, difficulty: float,
                 is_scam: bool = False, adversary: dict | None = None):
        self.session_id = session_id
        self.is_scam = is_scam
        self.adv = {k: bool((adversary or {}).get(k)) and is_scam for k in ADVERSARY_KNOBS}
        self.priv = seeded_rng(session_id, "private")  # draws that must not disturb the main random stream
        self.user = user
        self.world = world
        self.rng = rng
        self.d = difficulty
        self.t = 0.0
        self.stage = Stage.NONE
        self.rows: list[dict] = []
        # context state
        self.call_active = False
        self.caller_kind = None
        self.call_video = None
        self.call_start_t = None
        self.caller_number = None
        self.caller_reported = None
        self.screen_share = False
        self.sideloaded = False
        self.accessibility = False
        # outcome tracking
        self.extraction_ts = None
        self.loss = 0.0
        self._added_payees: set[str] = set()
        self.syndicate: int | None = None  # every mule in a scam session comes from one syndicate

    # ---------- time / stage ----------
    def wait(self, lo: float, hi: float | None = None):
        dt = float(self.rng.uniform(lo, hi)) if hi is not None else float(lo)
        self.t += dt * (5.0 if self.adv["slow"] else 1.0)

    def set_stage(self, stage: Stage):
        self.stage = stage

    def chance(self, p: float) -> bool:
        return bool(self.rng.random() < p)

    def intensity(self) -> float:
        """How strongly behavioural signals show up; weaker in harder sessions."""
        return float(np.clip(1.0 - 0.8 * self.d * self.rng.random(), 0.1, 1.0))

    # ---------- emit ----------
    def emit(self, event: Ev, **fields):
        row = dict.fromkeys(EVENT_COLUMNS)
        row.update(
            session_id=self.session_id, user_id=self.user.user_id, ts=round(self.t, 2),
            event=event.value, stage=self.stage.value,
            call_active=self.call_active, caller_kind=self.caller_kind, call_video=self.call_video,
            call_elapsed_s=round(self.t - self.call_start_t, 2) if self.call_active else None,
            caller_number=self.caller_number, caller_reported=self.caller_reported,
            screen_share_active=self.screen_share, sideloaded_app_present=self.sideloaded,
            accessibility_granted=self.accessibility,
        )
        row.update(fields)
        self.rows.append(row)
        self.t += float(self.rng.uniform(0.5, 3.0))  # events never share a timestamp

    # ---------- channel events ----------
    def _number(self, caller_kind: str) -> tuple[str, bool]:
        voip = caller_kind == "voip_intl"
        if caller_kind == "contact":
            return telecom.contact_number(self.user.user_id)
        if self.is_scam:
            if self.adv["fresh_numbers"]:
                return telecom.fresh_number(self.priv)
            synd = int(self.priv.integers(self.world.n_syndicates))
            return telecom.syndicate_number(synd, int(self.priv.integers(telecom.NUMBERS_PER_SYNDICATE)), voip)
        return telecom.genuine_number(int(self.priv.integers(telecom.GENUINE_POOL)), voip)

    def call_start(self, caller_kind: str, video: bool = False):
        if self.adv["no_call"]:
            return
        self.call_active, self.caller_kind, self.call_video, self.call_start_t = True, caller_kind, video, self.t
        self.caller_number, self.caller_reported = self._number(caller_kind)
        self.emit(Ev.CALL_START)

    def call_end(self):
        if not self.call_active:
            return
        self.emit(Ev.CALL_END)
        self.call_active, self.caller_kind, self.call_video, self.call_start_t = False, None, None, None
        self.caller_number = self.caller_reported = None

    def sms(self, sender_kind: str, has_link: bool):
        self.emit(Ev.SMS_RECEIVED, sms_sender_kind=sender_kind, sms_has_link=has_link)

    def link_click(self):
        self.emit(Ev.LINK_CLICK)

    def install(self, source: str):
        if self.adv["clean_device"]:
            source = "play_store"
        if source == "sideload":
            self.sideloaded = True
        self.emit(Ev.APP_INSTALL, app_source=source)

    def grant_accessibility(self):
        if self.adv["clean_device"]:
            return
        self.accessibility = True
        self.emit(Ev.ACCESSIBILITY_GRANT)

    def screen_share_start(self):
        if self.adv["clean_device"]:
            return
        self.screen_share = True
        self.emit(Ev.SCREEN_SHARE_START)

    def screen_share_end(self):
        if self.screen_share:
            self.emit(Ev.SCREEN_SHARE_END)
            self.screen_share = False

    def otp(self):
        self.emit(Ev.OTP_RECEIVED)

    def open_upi(self):
        self.emit(Ev.UPI_APP_OPEN)

    def balance_check(self):
        self.emit(Ev.BALANCE_CHECK)

    def device_change(self):
        self.emit(Ev.DEVICE_CHANGE)

    # ---------- biometrics ----------
    def bio(self, profile: str, intensity: float = 1.0):
        if self.adv["calm_hands"]:
            profile, intensity = "normal", 1.0
        base = self.user.bio
        noise = self.rng.lognormal(0.0, 0.12, len(BIO_KEYS))
        vals = {}
        for i, k in enumerate(BIO_KEYS):
            if profile == "remote":
                target = REMOTE_ABS[k]
                v = base[k] + intensity * (target - base[k])
                v *= self.rng.lognormal(0.0, 0.03)  # injected touches are very regular
            else:
                f = 1.0 + intensity * (BIO_PROFILES[profile][i] - 1.0)
                v = base[k] * f * noise[i]
            vals[f"bio_{k}"] = round(float(v), 4)
        bank = self.world.hmog
        if bank is not None and self.user.hmog_subject is not None:
            g_rng = seeded_rng(self.session_id, len(self.rows), "gestures")
            vals["bio_ref"] = bank.window_ref(self.user.hmog_subject, profile, intensity, g_rng)
        self.emit(Ev.BIO_WINDOW, **vals)

    # ---------- money ----------
    def mule(self, merchant_front: bool | None = None) -> str:
        if self.syndicate is None:
            self.syndicate = self.world.sample_syndicate()
        return self.world.sample_mule(merchant_front, self.syndicate)

    def _payee_fields(self, payee_id: str) -> dict:
        p = self.world.payee(payee_id)
        is_merchant = bool(p["is_merchant_vpa"])  # merchant fronts look like shops
        known = self.user.known_merchants if p["kind"] == "merchant" else self.user.known_payees
        return dict(
            payee_id=payee_id,
            payee_is_merchant=is_merchant,  # verified merchant VPA flag, visible in UPI
            payee_is_new=payee_id not in known,
            payee_vpa_age_days=int(p["vpa_age_days"]),
            payee_mule_score=float(p["mule_score"]),
        )

    def pay(self, payee_id: str, amount: float, bio_profile: str | None = "normal", intensity: float = 1.0,
            open_app: bool = True):
        """UPI_APP_OPEN -> [PAYEE_ADD] -> [BIO_WINDOW] -> PAYMENT_ATTEMPT -> PAYMENT_SUCCESS."""
        amount = float(max(1.0, round(amount)))
        pf = self._payee_fields(payee_id)
        if open_app:
            self.open_upi()
        if pf["payee_is_new"] and payee_id not in self._added_payees:
            self._added_payees.add(payee_id)
            self.emit(Ev.PAYEE_ADD, **pf)
            self.wait(5, 40)
        if bio_profile is not None:
            self.bio(bio_profile, intensity)
        if self.stage == Stage.EXTRACTION and self.extraction_ts is None:
            self.extraction_ts = round(self.t, 2)
        parts = [amount]
        if self.adv["split_amounts"]:
            k = int(self.priv.integers(3, 6))
            parts = [float(max(1.0, round(amount / k)))] * k
        for i, part in enumerate(parts):
            if i:
                self.wait(20, 180)
            self.emit(Ev.PAYMENT_ATTEMPT, amount=part, **pf)
            self.wait(1, 6)
            self.emit(Ev.PAYMENT_SUCCESS, amount=part, **pf)
            if self.world.payee(payee_id)["is_mule"]:
                self.loss += part

    def credit(self, payee_id: str, amount: float):
        self.emit(Ev.CREDIT_RECEIVED, amount=float(round(amount)), **self._payee_fields(payee_id))
