"""Request/response models for the RAKSHAM API."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ml.sim.schema import Ev

EventType = Literal[tuple(e.value for e in Ev)]


class UserProfile(BaseModel):
    user_id: str
    avg_txn_amount: float = Field(gt=0, description="user's average UPI payment, INR")
    hmog_subject: int | None = Field(None, description="demo only: the held-out HMOG subject whose gestures enrol this customer's touch profile")
    bio_pressure_baseline: float | None = None
    bio_swipe_velocity_baseline: float | None = None
    bio_tap_interval_ms_baseline: float | None = None
    bio_hesitation_ms_baseline: float | None = None
    bio_orientation_var_baseline: float | None = None


class SessionStart(BaseModel):
    user: UserProfile
    start_time: datetime
    consent: list[str] | None = Field(None, description="DPDP purposes the customer consented to "
                                      "(fraud_prevention, telecom_reputation, behavioural_biometrics); default: all")


class SessionEvent(BaseModel):
    """A raw event. Call/screen-share/app context is tracked server-side; send only what happened."""
    event: EventType
    ts: float = Field(ge=0, description="seconds since session start; non-decreasing")
    caller_kind: Literal["contact", "unknown", "voip_intl"] | None = None
    call_video: bool | None = None
    caller_number: str | None = Field(None, description="CALL_START: the calling number (checked against telecom reports via PSI)")
    sms_sender_kind: Literal["bank_shortcode", "unknown"] | None = None
    sms_has_link: bool | None = None
    app_source: Literal["play_store", "sideload"] | None = None
    payee_id: str | None = None
    payee_is_merchant: bool | None = None
    payee_is_new: bool | None = None
    payee_vpa_age_days: float | None = None
    payee_mule_score: float | None = Field(None, ge=0, le=1, description="payee intelligence (GNN account score slot)")
    amount: float | None = Field(None, ge=0)
    bio_pressure: float | None = None
    bio_swipe_velocity: float | None = None
    bio_tap_interval_ms: float | None = None
    bio_hesitation_ms: float | None = None
    bio_orientation_var: float | None = None
    gestures: list[dict[str, float | None]] | None = Field(
        None, description="BIO_WINDOW: 10-20 per-gesture feature dicts (ml.models.biometrics.data.FEATURES), scored by the real model")


class ConsentCheck(BaseModel):
    principal: str
    purpose: str


class PSIDemo(BaseModel):
    bank_numbers: list[str] = Field(min_length=1, max_length=500)


class Transfer(BaseModel):
    timestamp: datetime
    from_bank: str
    from_account: str
    to_bank: str
    to_account: str
    amount_paid: float = Field(ge=0)
    amount_received: float = Field(ge=0)
    payment_currency: str
    receiving_currency: str
    payment_format: str
    record: bool = Field(True, description="add this transfer to the online history after scoring")


class Gestures(BaseModel):
    user_id: str
    gestures: list[dict[str, float | None]] = Field(description="per-gesture features (ml.models.biometrics.data.FEATURES)")


class TabularRequest(BaseModel):
    transactions: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class PayeeQuery(BaseModel):
    """Payer-side question at payment time: how risky is this payee for this amount?"""
    payee_id: str
    amount: float = Field(gt=0)
    payer_id: str | None = None
    ts: datetime | float | None = Field(None, description="payment time (ISO) or seconds on the ledger clock; default: latest ledger time")
    payee_age_days: float | None = Field(None, ge=0, description="account age if the payee is not yet known to the ledger")
    payee_is_merchant: bool | None = None


class LedgerTransfer(BaseModel):
    """One completed transfer as the receiving side sees it."""
    ts: datetime | float
    src: str
    dst: str
    amount: float = Field(gt=0)
    src_bank: int = 0
    src_is_account: bool = Field(False, description="true if the sender is itself a tracked account (mule hop), false for an ordinary payer")
    dst_age_days: float | None = Field(None, ge=0)
    dst_is_merchant: bool | None = None


class DemoLoad(BaseModel):
    until_day: float = Field(80.0, ge=1, le=90)
    n_sessions: int = Field(3000, ge=500, le=20000)
    ambient_scale: float = Field(0.4, ge=0.1, le=1.0)


class HoldRequest(BaseModel):
    analyst: str = Field(min_length=1)
    reason: str = ""


# ---------------------------------------------------------------------------- transaction authentication (PRAMAAN)
class AuthDevice(BaseModel):
    device_id: str = Field(description="stable device identifier from the SDK (app install ID / FingerprintJS visitor ID)")
    platform: Literal["android", "ios", "web"] | None = None
    is_emulator: bool = False
    is_rooted: bool = False
    remote_access_app: bool = Field(False, description="a remote-control / screen-mirroring app is running")
    screen_share_active: bool = False
    sim_change_hours: float | None = Field(None, ge=0, description="hours since the SIM in this phone changed (SDK / telecom API); null = unknown")


class AuthNetwork(BaseModel):
    ip: str | None = Field(None, description="client IP (the API also reads it from the request)")
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    city: str | None = Field(None, description="usually from the load balancer's geo header X-Client-Geo-Location")


class AuthBehaviour(BaseModel):
    gestures: list[dict[str, float | None]] | None = Field(
        None, description="last 10-20 touch gestures (ml.models.biometrics.data.FEATURES), verified against the user's enrolled profile")
    keystrokes: list[float] | None = Field(
        None, min_length=31, max_length=31,
        description="one password / PIN attempt: 31 key timings in seconds (per key pair: hold, down-down, up-down; "
                    "then the last key's hold; ml.models.keystroke.data.COLUMNS), verified against the typing profile")
    time_to_submit_s: float | None = Field(None, ge=0, description="seconds from opening the payment screen to submit")
    input_events: int | None = Field(None, ge=0, description="touch / key / pointer events before submit")
    unknown_call_active: bool = Field(False, description="the phone is on a call with a number not in contacts")


class AuthTransaction(BaseModel):
    amount: float = Field(0.0, ge=0, description="INR; 0 for a login")
    payee_id: str | None = None
    payee_is_merchant: bool | None = None
    payee_risk: float | None = Field(None, ge=0, le=1, description="receiving-account risk if the caller has it; "
                                     "otherwise taken from payee intelligence when the account is known")


class AuthRequest(BaseModel):
    """One login or payment to decide: allow, challenge (and which challenge) or block."""
    request_id: str | None = Field(None, description="idempotency / correlation id; becomes decision_id")
    user_id: str
    ts: datetime | None = Field(None, description="event time; default: now")
    channel: Literal["mobile", "web"] = "mobile"
    event_type: Literal["payment", "login"] = "payment"
    device: AuthDevice
    network: AuthNetwork = AuthNetwork()
    behaviour: AuthBehaviour = AuthBehaviour()
    transaction: AuthTransaction = AuthTransaction()


class KeystrokeEnroll(BaseModel):
    user_id: str
    attempts: list[list[float]] = Field(min_length=5, description="password / PIN attempts, 31 timings each")


class KeystrokeVerify(BaseModel):
    user_id: str
    attempt: list[float] = Field(min_length=31, max_length=31, description="one password / PIN attempt, 31 timings")


class ChallengeResult(BaseModel):
    decision_id: str
    passed: bool = Field(description="did the user complete the step-up (OTP / passkey / call-back / cool-off)?")
