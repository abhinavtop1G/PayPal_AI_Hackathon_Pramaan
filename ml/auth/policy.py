"""Decision policy: allow / challenge / block, and *which* challenge.

1. Pick the step-up that fits the signals that fired (a challenge the attacker can pass is friction for nothing):
     coaching signs on the owner's own device (unknown call / screen share, own hands)  -> cool_off
         an OTP or passkey does not help when the real owner is being talked into paying
     remote-access app, or someone else's hands on a shared screen                     -> bank_callback
     SIM changed in the last 7 days                                                    -> passkey
         never SMS OTP: after a SIM swap the OTP goes to the attacker
     new / untrusted device and the user has another trusted device                    -> passkey
         approve on the registered device (device-bound key + biometric)
     otherwise                                                                         -> sms_otp
2. Expected cost of each action with fused risk p and exposure A (payment amount; a nominal value for logins):
     allow:      p * A
     challenge:  p * A * (1 - efficacy[c]) + (1 - p) * friction[c]    (also tried with bank_callback: escalation)
     block:      (1 - p) * block_cost                                  (only if p >= block_min_p)
   choose the cheapest. Efficacies and frictions are assumptions (rupee-equivalents) to be tuned with the bank.
3. Hard rules: block after a failed challenge in the last 30 minutes; never allow a request that both comes from
   an emulator and through a datacenter / anonymiser IP without a challenge; device binding: the first payment from
   a device never seen on the account is always challenged.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CHALLENGES = ("sms_otp", "passkey", "bank_callback", "cool_off")

# P(challenge stops the attack | attack type). Used only by the evaluation replay; assumptions, documented in the report.
EFFICACY = {
    "sms_otp":       {"ato_new_device": 0.50, "sim_swap": 0.00, "bot": 0.90, "remote_access": 0.20, "coerced": 0.05},
    "passkey":       {"ato_new_device": 0.95, "sim_swap": 0.95, "bot": 0.99, "remote_access": 0.40, "coerced": 0.10},
    "bank_callback": {"ato_new_device": 0.90, "sim_swap": 0.30, "bot": 0.99, "remote_access": 0.85, "coerced": 0.60},
    "cool_off":      {"ato_new_device": 0.60, "sim_swap": 0.50, "bot": 0.90, "remote_access": 0.60, "coerced": 0.50},
}
# P(a genuine user completes the challenge); the rest abandon (a lost payment, counted as friction)
GENUINE_PASS = {"sms_otp": 0.97, "passkey": 0.98, "bank_callback": 0.90, "cool_off": 0.85}

MESSAGES = {  # (English, Hindi). Hindi to be reviewed by a native speaker before user-facing use.
    "allow": ("Payment approved.", "भुगतान स्वीकृत।"),
    "sms_otp": ("Enter the one-time password sent to your registered mobile number.",
                "अपने रजिस्टर्ड मोबाइल नंबर पर भेजा गया OTP दर्ज करें।"),
    "passkey": ("Approve this payment on your registered device with your fingerprint or face.",
                "अपने रजिस्टर्ड डिवाइस पर फ़िंगरप्रिंट या चेहरे से इस भुगतान को स्वीकृत करें।"),
    "bank_callback": ("Your bank will call you on your registered number to confirm this payment.",
                      "इस भुगतान की पुष्टि के लिए आपका बैंक आपके रजिस्टर्ड नंबर पर कॉल करेगा।"),
    "cool_off": ("We've paused this payment for 30 minutes. If someone on a call is asking you to pay, hang up: "
                 "banks and police never do this. Report fraud at 1930.",
                 "हमने यह भुगतान 30 मिनट के लिए रोका है। अगर कॉल पर कोई आपसे भुगतान करवाना चाहता है तो कॉल काट दें: बैंक और "
                 "पुलिस ऐसा कभी नहीं करते। धोखाधड़ी की शिकायत 1930 पर करें।"),
    "block": ("This payment was blocked to protect your account. Call your bank's helpline if this was you.",
              "आपके खाते की सुरक्षा के लिए यह भुगतान रोका गया है। अगर यह आप थे, तो अपने बैंक की हेल्पलाइन पर कॉल करें।"),
    "bank_callback_coached": ("Your bank will call you on your registered number before this payment goes through. If "
                              "someone on a call is telling you to pay, hang up: banks and police never do this. Report "
                              "fraud at 1930.",
                              "यह भुगतान होने से पहले आपका बैंक आपके रजिस्टर्ड नंबर पर कॉल करेगा। अगर कॉल पर कोई आपसे भुगतान करवा "
                              "रहा है तो कॉल काट दें: बैंक और पुलिस ऐसा कभी नहीं करते। धोखाधड़ी की शिकायत 1930 पर करें।"),
    "block_coached": ("This payment was stopped. If someone on a call or screen share is telling you to pay, it is a scam: "
                      "banks, police and courts never ask for payments like this. Hang up and report it at 1930.",
                      "यह भुगतान रोका गया है। अगर कॉल या स्क्रीन शेयर पर कोई आपसे भुगतान करवा रहा है, तो यह ठगी है: बैंक, पुलिस "
                      "और अदालतें कभी ऐसे भुगतान नहीं माँगतीं। कॉल काटें और 1930 पर शिकायत करें।"),
}


@dataclass
class AuthPolicy:
    efficacy: dict = field(default_factory=lambda: {"sms_otp": 0.55, "passkey": 0.90, "bank_callback": 0.85, "cool_off": 0.55})
    friction: dict = field(default_factory=lambda: {"sms_otp": 8.0, "passkey": 6.0, "bank_callback": 60.0, "cool_off": 40.0})
    block_cost: float = 400.0         # a genuine payment refused: lost sale, support call, churn risk
    login_exposure: float = 20000.0   # value at risk behind a login (no amount)
    fail_block_window_s: float = 1800.0
    block_min_p: float = 0.5          # block only when an attack is more likely than not

    def choose_challenge(self, f: dict, ctx: dict) -> str:
        own_hands = not (f.get("bio_dev") == f.get("bio_dev") and f.get("bio_dev", 0) > 0.5)  # NaN-safe
        own_device = ctx.get("device_trusted", False)
        if f.get("remote_access_app") or (f.get("screen_share_active") and not own_hands):
            return "bank_callback"
        if own_device and own_hands and (f.get("unknown_call_active") or f.get("screen_share_active")):
            return "cool_off"
        if f.get("sim_fresh", 0) > 0:
            return "passkey"
        if (f.get("device_new") or f.get("device_untrusted")) and ctx.get("has_other_trusted_device"):
            return "passkey"
        return "sms_otp"

    def decide(self, p: float, amount: float, f: dict, ctx: dict) -> dict:
        A = amount if amount and amount > 0 else self.login_exposure
        c = self.choose_challenge(f, ctx)
        # escalation: a large amount at moderate risk gets a stronger challenge, not a block. Bank call-back is the
        # strongest generic step-up, except after a SIM change (the call would reach the attacker's SIM).
        options = [c] if (c == "bank_callback" or f.get("sim_fresh", 0) > 0) else [c, "bank_callback"]
        ch_cost = {o: p * A * (1 - self.efficacy[o]) + (1 - p) * self.friction[o] for o in options}
        c = min(ch_cost, key=ch_cost.get)
        cost = {"allow": p * A, "challenge": ch_cost[c], "block": (1 - p) * self.block_cost}
        if p < self.block_min_p:  # never refuse outright on a minority belief: challenge instead
            cost["block"] = float("inf")
        action = min(cost, key=cost.get)
        rule = None
        if ctx.get("last_fail_age_s") is not None and ctx["last_fail_age_s"] <= self.fail_block_window_s:
            action, rule = "block", "recent_failed_challenge"
        elif action == "allow" and f.get("emulator") and (f.get("ip_datacenter") or f.get("ip_anonymiser")):
            action, rule = "challenge", "emulator_on_hosting_ip"
        elif action == "allow" and f.get("device_new") and (amount or 0) > 0:
            # device binding: the first payment from a device never seen on this account is always stepped up, however
            # low the risk. This is what stops a SIM swap that looks ordinary in every other way.
            action, rule, c = "challenge", "new_device_binding", self.choose_challenge(f, ctx)
        return {"decision": action, "challenge_type": c if action == "challenge" else None, "rule": rule,
                "expected_cost": {k: (round(v, 2) if v != float("inf") else None) for k, v in cost.items()}}


def message(decision: str, challenge_type: str | None, coached: bool = False) -> tuple[str, str]:
    """User-facing text. A blocked payment made on the customer's own device during an unknown call / screen share is
    most likely a coached victim: they get the scam warning, not a 'your account is protected' notice."""
    if coached and decision == "block":
        return MESSAGES["block_coached"]
    if coached and decision == "challenge" and challenge_type == "bank_callback":
        return MESSAGES["bank_callback_coached"]
    return MESSAGES[challenge_type if decision == "challenge" else decision]
