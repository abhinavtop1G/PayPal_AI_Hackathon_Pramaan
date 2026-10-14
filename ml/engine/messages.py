"""User-facing alert text (English + Hindi), chosen by predicted workflow and action tier.

Hindi strings should be reviewed by a native speaker before any user-facing use.
1930 is India's National Cyber Crime Helpline.
"""
TYPOLOGY_MSG = {
    "digital_arrest": (
        "Police, CBI or customs never ask you to transfer money or stay on a video call. This matches a "
        "'digital arrest' scam. Hang up and call 1930.",
        "पुलिस, CBI या कस्टम कभी भी पैसे ट्रांसफ़र करने या वीडियो कॉल पर बने रहने को नहीं कहते। यह 'डिजिटल अरेस्ट' "
        "ठगी जैसा है। कॉल काटें और 1930 पर कॉल करें।",
    ),
    "fake_kyc_apk": (
        "Banks never ask you to install apps from links or share OTPs to update KYC. Uninstall the app you just "
        "installed and call your bank.",
        "बैंक कभी भी लिंक से ऐप इंस्टॉल करने या KYC अपडेट के लिए OTP शेयर करने को नहीं कहते। अभी इंस्टॉल किया गया "
        "ऐप हटाएँ और अपने बैंक को कॉल करें।",
    ),
    "investment_task": (
        "Platforms that ask for 'tax' or 'upgrade fees' before you can withdraw earnings are a common investment "
        "scam. Do not send more money.",
        "जो प्लेटफ़ॉर्म कमाई निकालने से पहले 'टैक्स' या 'अपग्रेड फ़ीस' माँगते हैं, वह आम निवेश ठगी है। और पैसे न भेजें।",
    ),
    "voice_clone_relative": (
        "Callers can clone a relative's voice. Before paying, call your relative back on the number saved in your "
        "phone.",
        "ठग किसी रिश्तेदार की आवाज़ की नकल कर सकते हैं। पैसे भेजने से पहले उन्हें आपके फ़ोन में सेव किए गए नंबर पर "
        "वापस कॉल करें।",
    ),
}
GENERIC = ("This payment looks unusual: {reasons}. Take a moment before you pay.",
           "यह भुगतान असामान्य लग रहा है। भुगतान से पहले एक बार रुककर सोचें।")
TIER_PREFIX = {
    "nudge": ("", ""),
    "cool_off": ("We've paused this payment for 10 minutes. ", "हमने यह भुगतान 10 मिनट के लिए रोका है। "),
    "hold": ("This payment is on hold and your bank will call you on your registered number. ",
             "यह भुगतान रोका गया है और आपका बैंक आपके रजिस्टर्ड नंबर पर कॉल करेगा। "),
}


def render(tier: str, typology: str | None, reasons: list[str]) -> tuple[str, str]:
    en, hi = TYPOLOGY_MSG.get(typology, GENERIC)
    en = en.format(reasons="; ".join(reasons) or "unusual activity")
    pre_en, pre_hi = TIER_PREFIX.get(tier, ("", ""))
    return pre_en + en, pre_hi + hi
