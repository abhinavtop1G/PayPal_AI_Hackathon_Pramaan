"""Event vocabulary, stage labels and output column schema for the scam-workflow simulator."""
from enum import Enum


class Stage(str, Enum):
    NONE = "none"            # benign session
    CONTACT = "contact"      # first touch: call / SMS / link
    PRETEXT = "pretext"      # story is built: "your parcel has drugs", "KYC expiring", "invest & earn"
    ISOLATION = "isolation"  # victim is kept on the line / made to install tools / trust is groomed
    EXTRACTION = "extraction"  # money leaves


STAGE_ORDER = {Stage.NONE: 0, Stage.CONTACT: 1, Stage.PRETEXT: 2, Stage.ISOLATION: 3, Stage.EXTRACTION: 4}


class Ev(str, Enum):
    CALL_START = "CALL_START"
    CALL_END = "CALL_END"
    SMS_RECEIVED = "SMS_RECEIVED"
    LINK_CLICK = "LINK_CLICK"
    APP_INSTALL = "APP_INSTALL"
    ACCESSIBILITY_GRANT = "ACCESSIBILITY_GRANT"
    SCREEN_SHARE_START = "SCREEN_SHARE_START"
    SCREEN_SHARE_END = "SCREEN_SHARE_END"
    OTP_RECEIVED = "OTP_RECEIVED"
    UPI_APP_OPEN = "UPI_APP_OPEN"
    BALANCE_CHECK = "BALANCE_CHECK"
    PAYEE_ADD = "PAYEE_ADD"
    PAYMENT_ATTEMPT = "PAYMENT_ATTEMPT"  # interception point: an alert must fire at or before this
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    CREDIT_RECEIVED = "CREDIT_RECEIVED"
    BIO_WINDOW = "BIO_WINDOW"            # summary of a few seconds of touch/motion telemetry
    DEVICE_CHANGE = "DEVICE_CHANGE"      # UPI re-bound to a new device / SIM


SCAM_TYPOLOGIES = ["digital_arrest", "fake_kyc_apk", "investment_task", "voice_clone_relative"]
BENIGN_TYPOLOGIES = [
    "routine",            # small merchant payments
    "family_transfer",    # large payment to a known payee, sometimes while on a call with a contact
    "new_payee_service",  # on call with an unknown number, paying a new payee (delivery / plumber)
    "large_new_payee",    # rent / deposit to a new payee
    "urgent_bill",        # rushed but legitimate bill payment
    "support_install",    # installs an app / screen-shares with genuine support, no anomalous payment
    # legitimate look-alikes of each scam workflow (hard negatives)
    "hospital_emergency",     # ~ digital arrest: long unknown call -> large stressed payment to new payee
    "bank_app_update",        # ~ fake KYC: bank SMS link -> install -> OTP -> payments
    "legit_investing",        # ~ investment scam: escalating deposits to a broker, credits back
    "genuine_urgent_family",  # ~ voice clone: relative on a new number needs money urgently
]

# caller_kind: "contact" (in phonebook) | "unknown" (Indian mobile, not saved) | "voip_intl" (VoIP / +international)
CALLER_KINDS = ["contact", "unknown", "voip_intl"]

# Every event row has exactly these columns (None/NaN where not applicable).
EVENT_COLUMNS = [
    # identity / time
    "session_id", "user_id", "ts", "event_time", "event", "stage",
    # session context snapshot at this event
    "call_active", "caller_kind", "call_video", "call_elapsed_s", "caller_number", "caller_reported",
    "screen_share_active", "sideloaded_app_present", "accessibility_granted",
    # event-specific
    "sms_sender_kind", "sms_has_link", "app_source",
    "payee_id", "payee_is_merchant", "payee_is_new", "payee_vpa_age_days", "payee_mule_score", "amount",
    "bio_pressure", "bio_swipe_velocity", "bio_tap_interval_ms", "bio_hesitation_ms", "bio_orientation_var",
    # reference to the real HMOG gestures behind a BIO_WINDOW (ml/sim/hmog_bank.py); None without the HMOG cache
    "bio_ref",
    # the real biometrics model's deviation for that window (filled by ml/models/biometrics/session_scores.py offline,
    # by the session API online); > 0 means the touches don't match the enrolled customer
    "bio_model_dev",
]

SESSION_COLUMNS = [
    "session_id", "user_id", "typology", "is_scam", "start_time", "n_events",
    "extraction_ts", "loss_amount", "difficulty",
]
