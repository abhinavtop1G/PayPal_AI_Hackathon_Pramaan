"""Plain-language case summaries (English + Hindi) built from numbers, never from free text.

The summary only restates facts the tracker already computed (counts, rupees, reason codes), so an analyst can
check every sentence against the case card. A language model is deliberately *not* in this path: it may be
added later to rephrase these templates, but it must not decide or invent.

Hindi strings should be reviewed by a native speaker before any user-facing use.
"""
from .campaigns import Case

H = 3600.0

REASON_HI = {
    "very new account": "बहुत नया खाता",
    "account was dormant and has just become active": "खाता निष्क्रिय था और अभी अचानक सक्रिय हुआ है",
    "many credits in the last hour": "पिछले एक घंटे में बहुत सारे क्रेडिट",
    "many credits in the last 24 hours": "पिछले 24 घंटे में बहुत सारे क्रेडिट",
    "many different people paid this account within the hour": "एक घंटे में कई अलग-अलग लोगों ने इस खाते में पैसे भेजे",
    "many different people paid this account today": "आज कई अलग-अलग लोगों ने इस खाते में पैसे भेजे",
    "almost every payer is paying this account for the first time": "लगभग हर भेजने वाला इस खाते में पहली बार पैसे भेज रहा है",
    "money arrives from many different banks": "पैसा कई अलग-अलग बैंकों से आ रहा है",
    "large total received in 24 hours": "24 घंटे में कुल बड़ी रकम मिली",
    "unusually large typical credit": "सामान्य क्रेडिट असामान्य रूप से बड़ा है",
    "payments are round-number amounts": "भुगतान गोल रकम के हैं",
    "this payment is large": "यह भुगतान बड़ा है",
    "this payment is far larger than the account's usual credits": "यह भुगतान खाते के सामान्य क्रेडिट से कहीं बड़ा है",
    "first payment from this payer": "इस भेजने वाले का पहला भुगतान",
    "most received money was sent onward within the hour": "मिला हुआ ज़्यादातर पैसा एक घंटे में आगे भेज दिया गया",
    "most received money was sent onward within a day": "मिला हुआ ज़्यादातर पैसा एक दिन में आगे भेज दिया गया",
    "money is split across many accounts": "पैसा कई खातों में बाँटा जा रहा है",
    "money stays only minutes before moving on": "पैसा कुछ ही मिनट रुककर आगे चला जाता है",
    "money is sent out and returned in matching amounts": "पैसा बाहर भेजा जाता है और उसी रकम में वापस आता है",
    "receives money forwarded from a flagged account": "संदिग्ध खाते से आगे भेजा गया पैसा मिल रहा है",
    "behaviour matches known mule accounts": "व्यवहार ज्ञात म्यूल खातों जैसा है",
}


def _age(hours: float) -> tuple[str, str]:
    if hours >= 48:
        d = hours / 24
        return f"{d:.0f} days", f"{d:.0f} दिन"
    return f"{hours:.0f} h", f"{hours:.0f} घंटे"


def _inr(x: float) -> str:
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} lakh"
    return f"₹{x:,.0f}"


def actions_for(case: Case) -> list[dict]:
    acts = [{"action": "credit_hold", "label": "Place a transaction-level hold on credits to the accounts we host",
             "needs_human": True},
            {"action": "report_1930", "label": "File a 1930 / NCRP report with the evidence pack", "needs_human": True}]
    if case.victims_24h:
        acts.append({"action": "warn_payers", "label": f"Warn the {case.victims_24h} payers active in the last 24 hours", "needs_human": False})
    if case.novel:
        acts.append({"action": "review_pattern", "label": "Review as a possible new scam pattern; confirmed accounts become training labels",
                     "needs_human": True})
    return acts


def case_summary(case: Case, now: float) -> dict:
    age_en, age_hi = _age(max(0.0, (now - case.opened_ts) / H))
    reasons = case.reasons or ["behaviour matches known mule accounts"]
    why_en = "; ".join(reasons)
    why_hi = "; ".join(REASON_HI.get(r, r) for r in reasons)
    en = (f"{case.n_victims} people have paid {len(case.accounts)} linked accounts, {_inr(case.loss_in)} in total, and about "
          f"{_inr(case.recoverable)} is still sitting in these accounts. Case opened {age_en} ago. Why: {why_en}.")
    hi = (f"{case.n_victims} लोगों ने आपस में जुड़े {len(case.accounts)} खातों में कुल {_inr(case.loss_in)} भेजे हैं और लगभग "
          f"{_inr(case.recoverable)} अभी भी इन खातों में है। केस {age_hi} पहले खुला। कारण: {why_hi}।")
    if case.novel:
        en += " This does not match a known scam pattern."
        hi += " यह किसी ज्ञात ठगी पैटर्न से मेल नहीं खाता।"
    return {"en": en, "hi": hi, "actions": actions_for(case)}
