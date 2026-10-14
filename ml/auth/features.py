"""Request + live state -> model features. The same function runs in the simulator, in training and in the API, and it
only reads state written before the request, so training features are exactly what serving would have computed.

Request shape (what the client SDK / bank backend sends; see backend/schemas.py AuthRequest):
    user_id, ts (epoch seconds), channel, event_type ('payment' | 'login')
    device:      device_id, platform, is_emulator, is_rooted, remote_access_app, screen_share_active, sim_change_hours
    network:     ip, lat, lon, city                       (lat/lon/city usually from the load balancer's geo header)
    behaviour:   bio_dev (filled by the engine from gestures), time_to_submit_s, input_events, unknown_call_active
    transaction: amount, payee_id, payee_is_merchant, payee_risk
"""
from __future__ import annotations

import math

import numpy as np

from .geo import haversine_km, ip_kind
from .state import DAY, AuthState, _hour, device_trusted

# (name, family, monotone direction): risk can only rise with every feature (monotone XGBoost), so a signal can never
# argue *for* an attacker and the explanations always point the right way.
SPEC = [
    ("bio_dev", "behaviour", 1),            # touch gestures vs the user's enrolled profile (BiLSTM + LDA); NaN if no touch
    ("fast_submit", "behaviour", 1),        # form submitted in < 3 s (scripted)
    ("low_input", "behaviour", 1),          # almost no input events before submit
    ("unknown_call_active", "behaviour", 1),  # on a call with an unknown number while paying (coaching)
    ("screen_share_active", "behaviour", 1),
    ("device_new", "device", 1),            # device never seen for this user
    ("device_untrusted", "device", 1),      # seen, but not yet trusted (young, few uses, no strong challenge)
    ("n_devices_30d", "device", 1),
    ("accounts_on_device", "device", 1),    # other accounts used from this device in 30 days (device farm / stuffing)
    ("emulator", "device", 1),
    ("rooted", "device", 1),
    ("remote_access_app", "device", 1),
    ("sim_fresh", "device", 1),             # 1 = SIM changed just now, 0 = more than 7 days ago / never
    ("ip_datacenter", "device", 1),
    ("ip_anonymiser", "device", 1),
    ("ip_accounts_1h", "device", 1),        # accounts using this IP address in the last hour
    ("geo_speed", "device", 1),             # log1p(km/h) needed since the last completed transaction
    ("new_city", "device", 1),
    ("amt_z", "transaction", 1),            # amount vs the user's history (log scale)
    ("payee_new", "transaction", 1),
    ("payee_risk", "transaction", 1),       # receiving-account risk (payee intelligence)
    ("txn_count_1h", "transaction", 1),
    ("spend_24h_z", "transaction", 1),      # last-24h spend incl. this payment vs the user's usual payment
    ("hour_rarity", "transaction", 1),
    ("short_history", "transaction", 1),
    ("fails_24h", "transaction", 1),        # failed challenges in the last 24 h
]
FEATURES = [s[0] for s in SPEC]
FAMILY = {s[0]: s[1] for s in SPEC}
MONOTONE = tuple(s[2] for s in SPEC)
FAMILIES = ("behaviour", "device", "transaction")

PRIOR_LOG_AMT, PRIOR_SD = math.log1p(1000.0), 1.2

REASON = {  # feature -> (English, Hindi). Hindi to be reviewed by a native speaker before user-facing use.
    "bio_dev": ("touch pattern does not match the account owner", "टच करने का तरीका खाताधारक से मेल नहीं खाता"),
    "fast_submit": ("submitted faster than a person can type", "इतनी तेज़ी से भरा गया जितना कोई व्यक्ति टाइप नहीं कर सकता"),
    "low_input": ("almost no screen interaction before paying", "भुगतान से पहले लगभग कोई स्क्रीन गतिविधि नहीं"),
    "unknown_call_active": ("on a call with an unknown number while paying", "भुगतान के दौरान अनजान नंबर से कॉल चल रही है"),
    "screen_share_active": ("screen is being shared", "स्क्रीन शेयर की जा रही है"),
    "device_new": ("first time this device is used on the account", "इस खाते पर यह डिवाइस पहली बार इस्तेमाल हुआ"),
    "device_untrusted": ("device is not yet trusted for this account", "यह डिवाइस अभी इस खाते के लिए भरोसेमंद नहीं है"),
    "n_devices_30d": ("many devices used on this account recently", "हाल में इस खाते पर कई डिवाइस इस्तेमाल हुए"),
    "accounts_on_device": ("this device was used for several other accounts", "इस डिवाइस से कई अन्य खाते इस्तेमाल हुए"),
    "emulator": ("request comes from an emulator", "अनुरोध एमुलेटर से आया है"),
    "rooted": ("device is rooted / jailbroken", "डिवाइस रूटेड / जेलब्रोकन है"),
    "remote_access_app": ("a remote-access app is running", "रिमोट-एक्सेस ऐप चल रहा है"),
    "sim_fresh": ("SIM card was changed recently", "सिम कार्ड हाल ही में बदला गया"),
    "ip_datacenter": ("connection comes from a hosting provider, not a home or mobile network",
                      "कनेक्शन घर/मोबाइल नेटवर्क से नहीं, होस्टिंग सर्वर से है"),
    "ip_anonymiser": ("connection goes through a VPN / Tor", "कनेक्शन VPN / Tor से है"),
    "ip_accounts_1h": ("many accounts used from this IP address in the last hour",
                       "पिछले एक घंटे में इस IP से कई खाते इस्तेमाल हुए"),
    "geo_speed": ("location changed sharply since the last payment", "पिछले भुगतान के बाद स्थान में बड़ा बदलाव"),
    "new_city": ("payment from a city this account has never used", "ऐसे शहर से भुगतान जहाँ से यह खाता कभी इस्तेमाल नहीं हुआ"),
    "amt_z": ("amount is much larger than usual for this account", "राशि इस खाते के सामान्य भुगतान से बहुत अधिक है"),
    "payee_new": ("first payment to this payee", "इस प्राप्तकर्ता को पहला भुगतान"),
    "payee_risk": ("receiving account is linked to suspected fraud", "प्राप्तकर्ता खाता संदिग्ध धोखाधड़ी से जुड़ा है"),
    "txn_count_1h": ("many payments in the last hour", "पिछले एक घंटे में कई भुगतान"),
    "spend_24h_z": ("unusually high spending in the last 24 hours", "पिछले 24 घंटों में असामान्य रूप से अधिक खर्च"),
    "hour_rarity": ("unusual time of day for this account", "इस खाते के लिए असामान्य समय"),
    "short_history": ("account has little payment history", "खाते का भुगतान इतिहास बहुत कम है"),
    "fails_24h": ("failed verification attempts in the last 24 hours", "पिछले 24 घंटों में असफल सत्यापन प्रयास"),
}


def _f(x) -> float:
    return float(x) if x is not None else 0.0


def build(req: dict, state: AuthState) -> tuple[dict, dict]:
    """(features, context). Context carries what the policy needs to pick a challenge (not model inputs)."""
    now = float(req["ts"])
    uid = req["user_id"]
    u = state.user(uid, now)
    dev = req.get("device") or {}
    net = req.get("network") or {}
    beh = req.get("behaviour") or {}
    tx = req.get("transaction") or {}
    f: dict[str, float] = {}

    # behaviour
    f["bio_dev"] = float(beh["bio_dev"]) if beh.get("bio_dev") is not None else np.nan
    tts = beh.get("time_to_submit_s")
    f["fast_submit"] = float(tts is not None and tts < 3.0)
    n_in = beh.get("input_events")
    f["low_input"] = float(n_in is not None and n_in < 4)
    f["unknown_call_active"] = float(bool(beh.get("unknown_call_active")))
    f["screen_share_active"] = float(bool(dev.get("screen_share_active")))

    # device
    dev_id = dev.get("device_id")
    known = u["devices"].get(dev_id) if dev_id else None
    trusted_here = bool(known) and device_trusted(known, now)
    f["device_new"] = float(known is None)
    f["device_untrusted"] = float(known is not None and not trusted_here)
    f["n_devices_30d"] = float(sum(now - d["last"] <= 30 * DAY for d in u["devices"].values()) + (known is None))
    others = state.device_accounts(dev_id, now) if dev_id else {}
    f["accounts_on_device"] = float(len([x for x in others if x != uid]))
    f["emulator"] = float(bool(dev.get("is_emulator")))
    f["rooted"] = float(bool(dev.get("is_rooted")))
    f["remote_access_app"] = float(bool(dev.get("remote_access_app")))
    sim_h = dev.get("sim_change_hours")
    f["sim_fresh"] = max(0.0, 1.0 - float(sim_h) / 168.0) if sim_h is not None else 0.0
    kind = ip_kind(net.get("ip"))
    f["ip_datacenter"] = float(kind == "datacenter")
    f["ip_anonymiser"] = float(kind == "anonymiser")
    ip_users = state.ip_accounts(net["ip"], now) if net.get("ip") else {}
    f["ip_accounts_1h"] = float(len([x for x in ip_users if x != uid]))
    if u["geo"] and net.get("lat") is not None and net.get("lon") is not None:
        lat0, lon0, t0 = u["geo"]
        km = haversine_km(lat0, lon0, net["lat"], net["lon"])
        f["geo_speed"] = math.log1p(min(km / max((now - t0) / 3600.0, 0.25), 20000.0))
    else:
        f["geo_speed"] = np.nan
    f["new_city"] = float(u["n"] >= 3 and bool(net.get("city")) and net.get("city") not in u["cities"])

    # transaction
    amount = _f(tx.get("amount"))
    n, mean, m2 = u["amt"]
    if n >= 3:
        mu, sd = mean, max(math.sqrt(m2 / (n - 1)), 0.35)
    else:
        mu, sd = PRIOR_LOG_AMT, PRIOR_SD
    recent = [r for r in u["recent"] if now - r[0] <= DAY]
    if amount > 0:
        f["amt_z"] = (math.log1p(amount) - mu) / sd
        f["spend_24h_z"] = (math.log1p(amount + sum(r[1] for r in recent)) - mu) / sd
    else:
        f["amt_z"] = f["spend_24h_z"] = np.nan
    pid = tx.get("payee_id")
    f["payee_new"] = float(bool(pid) and pid not in u["payees"])
    f["payee_risk"] = float(tx["payee_risk"]) if tx.get("payee_risk") is not None else np.nan
    f["txn_count_1h"] = float(sum(now - r[0] <= 3600 for r in recent))
    f["hour_rarity"] = 1.0 - (u["hours"][_hour(now)] + 1) / (u["n"] + 24)
    f["short_history"] = float(u["n"] < 5)
    f["fails_24h"] = float(sum(now - t <= DAY for t in u["fails"]))

    trusted_devices = [k for k, d in u["devices"].items() if device_trusted(d, now)]
    ctx = {"device_trusted": trusted_here, "has_other_trusted_device": any(k != dev_id for k in trusted_devices),
           "ip_kind": kind, "history_n": u["n"],
           "last_fail_age_s": (now - max(u["fails"])) if u["fails"] else None}
    return {k: f[k] for k in FEATURES}, ctx
