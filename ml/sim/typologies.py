"""Scripts for each scam workflow and each benign look-alike.

Every script drives a SessionBuilder. Scams walk contact -> pretext -> isolation -> extraction;
benign sessions stay in Stage.NONE. `b.d` (difficulty, 0..1) drops or weakens cues so that
scams are not trivially separable and benign sessions borrow scam-like signals.
"""
from .builder import SessionBuilder
from .schema import Stage as S


def _round_amount(b: SessionBuilder, amount: float, p_round: float = 0.7) -> float:
    """Scammers dictate round figures ("transfer 50,000 for verification")."""
    if b.chance(p_round):
        step = 1000 if amount >= 5000 else 100
        return max(step, round(amount / step) * step)
    return amount


# =====================================================================================
# Scams
# =====================================================================================
def digital_arrest(b: SessionBuilder):
    """Fake police/CBI/customs officer keeps the victim on a long video call and makes them
    move money to a 'safe RBI account' to 'clear their name'."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.set_stage(S.CONTACT)
    if b.chance(0.5):  # IVR pre-call: "your parcel/SIM is blocked, press 9"
        b.call_start("voip_intl" if b.chance(0.6) else "unknown")
        b.wait(40, 150)
        b.call_end()
        b.wait(30, 600)
    b.call_start("voip_intl" if b.chance(0.75 - 0.35 * b.d) else "unknown", video=b.chance(0.65))
    b.wait(60, 300)

    b.set_stage(S.PRETEXT)
    b.bio("coerced", 0.5 * b.intensity())
    b.wait(300, 1500)
    if b.chance(0.5):  # told to install Skype / a "case portal"
        b.install("play_store")
        if b.chance(0.3):
            b.screen_share_start()

    b.set_stage(S.ISOLATION)
    for _ in range(int(rng.integers(1, 4))):
        b.wait(300, 1800)
        b.open_upi()
        b.balance_check()
        b.bio("coerced", b.intensity())
    if b.chance(0.05 + 0.2 * b.d):  # harder: call dropped, victim pays afterwards as instructed
        b.call_end()
        b.wait(120, 1800)

    b.set_stage(S.EXTRACTION)
    base = avg * rng.uniform(8, 40)
    mule = b.mule()
    for k in range(int(rng.integers(1, 5))):
        if k > 0 and b.chance(0.4):
            mule = b.mule()
        b.pay(mule, _round_amount(b, base * 1.4 ** k), "coerced", b.intensity())
        b.wait(120, 1200)
    b.screen_share_end()
    b.call_end()


def fake_kyc_apk(b: SessionBuilder):
    """'Your KYC expires today' SMS -> sideloaded APK with accessibility/overlay -> fast drain."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.set_stage(S.CONTACT)
    b.sms("bank_shortcode" if b.chance(0.25) else "unknown", has_link=True)  # sender IDs get spoofed
    if b.chance(0.4):  # "bank executive" call to push the link
        b.wait(30, 600)
        b.call_start("unknown")
    b.wait(30, 1800)

    b.set_stage(S.PRETEXT)
    b.link_click()
    b.wait(20, 120)
    b.install("play_store" if b.chance(0.1 * b.d) else "sideload")  # some droppers slip through the store

    b.set_stage(S.ISOLATION)
    if b.chance(0.95 - 0.35 * b.d):
        b.grant_accessibility()
    if b.chance(0.4):
        b.screen_share_start()
    b.otp()
    b.wait(60, 900)
    b.call_end()

    b.set_stage(S.EXTRACTION)
    attacker_device = b.chance(0.3)
    if attacker_device:  # UPI re-registered on the fraudster's phone via stolen OTP
        b.device_change()
    mule = b.mule()
    for k in range(int(rng.integers(2, 7))):
        if k > 0 and b.chance(0.3):
            mule = b.mule()
        # attacker-device payments carry no victim telemetry; overlay payments carry injected touches
        bio = None if attacker_device else "remote"
        b.pay(mule, avg * rng.uniform(3, 15), bio, b.intensity(), open_app=k == 0)
        b.wait(5, 40)
    b.screen_share_end()


def investment_task(b: SessionBuilder):
    """'Like YouTube videos / trade crypto and earn' — small payouts build trust, then big deposits."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.set_stage(S.CONTACT)
    b.sms("unknown", has_link=True)
    b.wait(60, 7200)

    b.set_stage(S.PRETEXT)
    b.link_click()
    b.wait(600, 3600)
    # deposits go to the "platform" account, often a merchant front; payouts come from other mules
    platform = b.mule(merchant_front=b.chance(0.6))
    stake = rng.uniform(200, 1000)
    b.pay(platform, stake, "normal", 1.0)
    b.wait(600, 3600)
    b.credit(b.mule(), stake * rng.uniform(1.2, 1.5))

    b.set_stage(S.ISOLATION)
    for _ in range(int(rng.integers(1, 4))):
        b.wait(3600, 86400)
        stake *= rng.uniform(1.5, 3.0)
        b.pay(platform, stake, "normal", 1.0)
        if b.chance(0.7):
            b.wait(600, 7200)
            b.credit(b.mule(), stake * rng.uniform(1.1, 1.4))

    b.set_stage(S.EXTRACTION)  # "pay tax / upgrade to VIP to withdraw"
    base = avg * rng.uniform(10, 60)
    for k in range(int(rng.integers(1, 4))):
        b.wait(600, 7200)
        b.pay(platform if b.chance(0.7) else b.mule(), _round_amount(b, base * 1.5 ** k), "rushed",
              0.4 * b.intensity())


def voice_clone_relative(b: SessionBuilder):
    """Cloned voice of a son/nephew: 'I've been arrested / had an accident, send money now'."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.set_stage(S.CONTACT)
    b.call_start("voip_intl" if b.chance(0.2) else "unknown")
    b.wait(20, 60)

    b.set_stage(S.PRETEXT)
    b.wait(30, 120)
    b.set_stage(S.ISOLATION)  # "don't tell mom/dad", hand-off to "police officer"
    b.wait(10, 90)

    b.set_stage(S.EXTRACTION)
    mule = b.mule()
    b.pay(mule, _round_amount(b, avg * rng.uniform(10, 50)), "rushed", b.intensity())
    if b.chance(0.3):
        b.wait(60, 400)
        b.pay(mule, _round_amount(b, avg * rng.uniform(5, 30)), "rushed", b.intensity(), open_app=False)
    b.call_end()


# =====================================================================================
# Everyday background activity
# =====================================================================================
def background(b: SessionBuilder, scale: float = 1.0):
    """Ordinary activity that also produces 'scammy-looking' events, so no event type is exclusive to
    scams: balance checks, spam SMS with links, refunds/credits from known parties, purchase OTPs,
    the odd sideloaded app or accessibility grant (password manager, reading aid) and new phones.
    Runs at the current stage (Stage.NONE when called before a script)."""
    rng, avg = b.rng, b.user.avg_txn_amount
    if b.chance(0.30 * scale):
        b.open_upi()
        b.balance_check()
        b.wait(30, 900)
    if b.chance(0.25 * scale):  # promotional / spam SMS
        b.sms("unknown", has_link=True)
        if b.chance(0.2):
            b.wait(10, 300)
            b.link_click()
        b.wait(30, 1800)
    if b.chance(0.20 * scale):  # refund, split-bill payback, salary
        b.credit(str(rng.choice(b.user.known_payees + b.user.known_merchants)), avg * rng.uniform(0.5, 10))
        b.wait(30, 1800)
    if b.chance(0.15 * scale):  # OTP for an online purchase
        b.otp()
        b.wait(5, 60)
        b.pay(b.world.sample_merchant(b.user), avg * rng.uniform(0.5, 4), "normal", 1.0)
        b.wait(30, 1800)
    if b.chance(0.04 * scale):
        b.install("sideload" if b.chance(0.5) else "play_store")
        if b.chance(0.6):
            b.grant_accessibility()
        b.wait(60, 1800)
    if b.chance(0.02 * scale):  # moved to a new phone
        b.device_change()
        b.wait(60, 1800)


# =====================================================================================
# Benign look-alikes
# =====================================================================================
def routine(b: SessionBuilder):
    rng, avg = b.rng, b.user.avg_txn_amount
    for _ in range(int(rng.integers(1, 5))):
        if b.chance(0.15):
            b.call_start("contact")
        b.pay(b.world.sample_merchant(b.user), avg * rng.lognormal(-0.5, 0.6), "normal", 1.0)
        b.call_end()
        b.wait(60, 3600)


def family_transfer(b: SessionBuilder):
    rng, avg = b.rng, b.user.avg_txn_amount
    on_call = b.chance(0.5)
    if on_call:
        b.call_start("contact", video=b.chance(0.2))
        b.wait(30, 600)
    payee = str(rng.choice(b.user.known_payees))
    b.pay(payee, _round_amount(b, avg * rng.uniform(5, 40), 0.6), "distracted" if on_call else "normal", 1.0)
    b.wait(10, 300)
    b.call_end()


def new_payee_service(b: SessionBuilder):
    """Paying a plumber / delivery agent / seller while on the phone with them — the classic false positive."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.call_start("unknown" if b.chance(0.7) else "contact")
    b.wait(30, 300)
    b.pay(b.world.sample_new_personal(b.user), avg * rng.uniform(0.5, 4), "distracted", 1.0)
    b.wait(10, 120)
    b.call_end()


def large_new_payee(b: SessionBuilder):
    """Rent / deposit / tuition to someone new."""
    rng, avg = b.rng, b.user.avg_txn_amount
    if b.chance(0.3):
        b.call_start("contact")
        b.wait(30, 300)
    b.pay(b.world.sample_new_personal(b.user), _round_amount(b, avg * rng.uniform(8, 40), 0.9), "normal", 1.0)
    b.call_end()


def urgent_bill(b: SessionBuilder):
    rng, avg = b.rng, b.user.avg_txn_amount
    if b.chance(0.6):
        b.sms("bank_shortcode", has_link=True)
        b.wait(60, 3600)
        b.link_click()
    b.pay(b.world.sample_merchant(b.user), avg * rng.uniform(1, 8), "rushed", 0.6)


def support_install(b: SessionBuilder):
    """Genuine tech support / work call: installs an app, maybe screen-shares, no odd payment."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.call_start("unknown" if b.chance(0.5) else "contact")
    b.wait(60, 600)
    b.install("play_store")
    if b.chance(0.5):
        b.screen_share_start()
        b.wait(120, 900)
        b.screen_share_end()
    b.call_end()
    if b.chance(0.5):
        b.wait(300, 3600)
        b.pay(b.world.sample_merchant(b.user), avg * rng.lognormal(-0.3, 0.5), "normal", 1.0)


# ---- legitimate look-alikes of each scam workflow (hard negatives) ----
def hospital_emergency(b: SessionBuilder):
    """Digital-arrest look-alike: long call with an unknown number (hospital / lawyer / agent), then a
    large, stressed payment to a new payee."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.call_start("unknown" if b.chance(0.8) else "voip_intl", video=b.chance(0.2))
    b.wait(600, 3600)
    if b.chance(0.4):
        b.open_upi()
        b.balance_check()
        b.wait(60, 900)
    payee = b.world.sample_new_personal(b.user) if b.chance(0.6) else b.world.sample_merchant(b.user, p_known=0.0)
    b.pay(payee, _round_amount(b, avg * rng.uniform(8, 40), 0.7), "coerced" if b.chance(0.5) else "rushed", 0.6)
    b.wait(60, 1200)
    b.call_end()


def bank_app_update(b: SessionBuilder):
    """Fake-KYC look-alike: genuine bank SMS with a link, app install/update, OTP, then bill payments."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.sms("bank_shortcode" if b.chance(0.8) else "unknown", has_link=True)
    b.wait(60, 3600)
    b.link_click()
    b.wait(20, 300)
    b.install("play_store" if b.chance(0.9) else "sideload")
    if b.chance(0.2):
        b.grant_accessibility()
    b.otp()
    b.wait(30, 600)
    for k in range(int(rng.integers(1, 4))):
        b.pay(b.world.sample_merchant(b.user, p_known=0.6), avg * rng.uniform(0.5, 6), "normal", 1.0, open_app=k == 0)
        b.wait(10, 300)


def legit_investing(b: SessionBuilder):
    """Investment-scam look-alike: link from a broker, small then larger deposits, credits coming back."""
    rng, avg = b.rng, b.user.avg_txn_amount
    if b.chance(0.6):
        b.sms("unknown" if b.chance(0.5) else "bank_shortcode", has_link=True)
        b.wait(60, 7200)
        b.link_click()
        b.wait(600, 3600)
    broker = b.world.sample_merchant(b.user, p_known=0.0)
    stake = avg * rng.uniform(0.5, 3)
    for _ in range(int(rng.integers(2, 5))):
        b.pay(broker, stake, "normal", 1.0)
        if b.chance(0.6):
            b.wait(3600, 86400)
            b.credit(broker, stake * rng.uniform(0.9, 1.3))
        stake *= rng.uniform(1.2, 3.0)
        b.wait(3600, 86400)


def genuine_urgent_family(b: SessionBuilder):
    """Voice-clone look-alike: a relative calls from a new number and urgently needs money sent to a
    friend's account. Only payee intelligence can separate this from the scam."""
    rng, avg = b.rng, b.user.avg_txn_amount
    b.call_start("unknown" if b.chance(0.85) else "voip_intl")
    b.wait(30, 240)
    payee = b.world.sample_new_personal(b.user) if b.chance(0.7) else str(rng.choice(b.user.known_payees))
    b.pay(payee, _round_amount(b, avg * rng.uniform(5, 40)), "rushed", 0.8)
    b.wait(30, 300)
    b.call_end()


TYPOLOGY_FNS = {
    "hospital_emergency": hospital_emergency,
    "bank_app_update": bank_app_update,
    "legit_investing": legit_investing,
    "genuine_urgent_family": genuine_urgent_family,
    "digital_arrest": digital_arrest,
    "fake_kyc_apk": fake_kyc_apk,
    "investment_task": investment_task,
    "voice_clone_relative": voice_clone_relative,
    "routine": routine,
    "family_transfer": family_transfer,
    "new_payee_service": new_payee_service,
    "large_new_payee": large_new_payee,
    "urgent_bill": urgent_bill,
    "support_install": support_install,
}
