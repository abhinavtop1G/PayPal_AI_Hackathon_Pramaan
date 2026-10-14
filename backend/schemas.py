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
