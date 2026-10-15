"""Account-takeover simulator: genuine customers and attacks on them, as a time-ordered stream of authentication
requests in the exact shape the API receives.

Genuine customers (assumptions, not measurements): home city and a second city, 1-3 payments a day around their own
hours, regular payees + shared merchants + occasional new payees, log-normal amounts. Behaviours that look risky but
are genuine are built in on purpose: a new phone (half with a new SIM), trips to other cities, rare big purchases,
web logins without touch data, corporate VPNs, rooted phones, the odd unknown call while paying.

Attacks (each with a difficulty d in [0, 1]; harder attacks hide more signals):
    ato_new_device   stolen credentials used from the attacker's device; often an emulator / hosting IP / far city;
                     at high d a residential proxy in the victim's own city
    sim_swap         victim's number moved to the attacker's SIM: new device, SIM changed hours ago, night-time,
                     large payments to a mule
    bot              credential-stuffing / card-testing campaigns: one device or IP hits many accounts within an
                     hour, scripted input; at high d rotating devices, residential proxies, human-like timing
    remote_access    remote-control app on the victim's own phone: known device, home location, someone else's hands
    coerced          the real customer coached on a call: own device, own (stressed) hands, unknown call active
                     (at high d the call is on an app the bank cannot see), large payment to a new payee

Touch: every mobile request carries a reference to 10 real HMOG gestures (ml/sim/hmog_bank.py): the customer's own
held-out subject ('normal'), the same with a documented stress shift ('coerced'), or a different subject's real
gestures ('remote': someone else's hands). Without the HMOG cache, deviations are drawn from the measured
distributions saved in ml/auth/artifacts/bio_quantiles.json.
"""
from __future__ import annotations

import ipaddress
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .geo import ALL_PLACES, ANONYMISER, CITIES, DATACENTER, FOREIGN, haversine_km

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 1, 1, tzinfo=IST).timestamp()
DAY = 86400.0
ATTACKS = ("ato_new_device", "sim_swap", "bot", "remote_access", "coerced")
ATTACK_MIX = (0.30, 0.15, 0.0, 0.20, 0.35)  # per attacked customer (bots come as separate campaigns)
BIO_QUANTILES = Path("ml/auth/artifacts/bio_quantiles.json")
CITY_NAMES = list(CITIES)
CITY_W = np.array([10, 10, 9, 7, 7, 7, 6, 5, 4, 4, 3, 3, 3, 2, 2, 0.3, 3, 3], dtype=float)
FRAUD_HUBS = ["Jamtara", "Kolkata", "Delhi", "Patna", "Dubai", "Phnom Penh", "Bangkok"]


@dataclass
class SimConfig:
    n_users: int = 3000
    days: int = 60
    attacked_frac: float = 0.15       # share of customers attacked once in the period
    bot_campaigns: int = 20
    seed: int = 7


def _ip_in(cidr: str, rng) -> str:
    net = ipaddress.ip_network(cidr)
    return str(net.network_address + int(rng.integers(1, net.num_addresses - 1)))


def _resid_ip(rng) -> str:  # Indian mobile / broadband space (not in the hosting or anonymiser lists)
    a = rng.choice([49, 106, 117, 157, 223])
    return f"{a}.{int(rng.integers(32, 250))}.{int(rng.integers(0, 255))}.{int(rng.integers(1, 254))}"


def _loc(city: str, rng) -> dict:
    lat, lon = ALL_PLACES[city]
    return {"city": city, "lat": round(lat + rng.normal(0, 0.03), 4), "lon": round(lon + rng.normal(0, 0.03), 4)}


def _near_city(home: str) -> str:
    """The customer's second city: the nearest city at least 80 km away (weekend home, office in a nearby city)."""
    return min((c for c in CITY_NAMES if c != home and haversine_km(*CITIES[home], *CITIES[c]) >= 80),
               key=lambda c: haversine_km(*CITIES[home], *CITIES[c]))


def _far_city(home: str, rng, min_km: float = 500) -> str:
    far = [c for c in CITY_NAMES if haversine_km(*CITIES[home], *CITIES[c]) >= min_km]
    return str(rng.choice(far))


def _hour_ts(day: float, hour: float) -> float:
    return T0 + day * DAY + (hour % 24) * 3600.0


class _Ids:
    def __init__(self):
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"e{self.n:07d}"


def generate(cfg: SimConfig = SimConfig(), bank=None) -> list[dict]:
    """Time-ordered requests. Each carries `label` (is_attack, scenario, attack_id, difficulty) and, for touch
    windows, `bio_ref` (resolve with the HMOG bank) and `bio_profile`."""
    rng = np.random.default_rng(cfg.seed)
    trng = np.random.default_rng(cfg.seed + 1)   # typing draws: own stream, so the rest of the simulation is unchanged
    new_id = _Ids()
    n_subjects = len(bank.subjects) if bank is not None else 15
    users = []
    for i in range(cfg.n_users):
        home = str(rng.choice(CITY_NAMES, p=CITY_W / CITY_W.sum()))
        u = {"uid": f"u{i:05d}", "i": i, "home": home, "alt": _near_city(home),
             "subject": bank.subject_for(i) if bank is not None else i % n_subjects,
             "mu": math.log(float(rng.lognormal(math.log(700), 0.7))), "sigma": float(rng.uniform(0.5, 1.0)),
             "rate": float(rng.lognormal(math.log(1.3), 0.5)), "hour": float(rng.uniform(8, 22)),
             "payees": [f"p{i}-{j}" for j in range(int(rng.integers(4, 12)))], "device": f"d{i}a",
             "platform": str(rng.choice(["android", "ios"], p=[0.8, 0.2])), "rooted": bool(rng.random() < 0.02),
             "web": bool(rng.random() < 0.25), "vpn": bool(rng.random() < 0.04),
             "ips": [_resid_ip(rng), _resid_ip(rng)], "vpn_ip": _ip_in(str(rng.choice(ANONYMISER)), rng)}
        users.append(u)

    events: list[dict] = []

    def req(u, ts, *, device_id, channel="mobile", loc=None, ip=None, amount, payee, merchant=False, profile="normal",
            sim_h=None, emulator=False, rooted=None, remote_app=False, share=False, call=False, tts=None, inputs=None,
            event_type="payment", label=None, gestures=True):
        tts = tts if tts is not None else float(rng.lognormal(math.log(18), 0.5))
        inputs = inputs if inputs is not None else int(rng.integers(8, 60))
        r = {"event_id": new_id(), "user_id": u["uid"], "ts": float(ts), "channel": channel, "event_type": event_type,
             "device": {"device_id": device_id, "platform": "web" if channel == "web" else u["platform"],
                        "is_emulator": bool(emulator), "is_rooted": bool(u["rooted"] if rooted is None else rooted),
                        "remote_access_app": bool(remote_app), "screen_share_active": bool(share),
                        "sim_change_hours": None if sim_h is None else round(float(sim_h), 2)},
             "network": {"ip": ip or u["ips"][int(rng.integers(2))], **(loc or _loc(u["home"], rng))},
             "behaviour": {"time_to_submit_s": round(tts, 2), "input_events": int(inputs), "unknown_call_active": bool(call)},
             "transaction": {"amount": round(float(amount), 2) if event_type == "payment" else 0.0,
                             "payee_id": payee if event_type == "payment" else None, "payee_is_merchant": bool(merchant)},
             "label": label or {"is_attack": False, "scenario": "genuine", "attack_id": None, "difficulty": None},
             "bio_subject": u["subject"]}
        if channel == "mobile" and gestures:
            r["bio_profile"] = profile
        # password / PIN entry: every login, every web payment, half of mobile payments carry one typed attempt
        if event_type == "login" or channel == "web" or trng.random() < 0.5:
            r["typing_owner"] = u["i"]
            r["typing_profile"] = ("bot" if r["label"]["scenario"] == "bot" else
                                   profile if profile in ("remote", "coerced") else "normal")
        events.append(r)
        return r

    # ------------------------------------------------------------------ genuine activity
    for u in users:
        n = rng.poisson(u["rate"] * cfg.days)
        days = np.sort(rng.uniform(0, cfg.days, n))
        phone_day = float(rng.uniform(5, cfg.days - 5)) if rng.random() < 0.08 else None
        phone_sim = phone_day is not None and rng.random() < 0.5
        trip = (float(rng.uniform(3, cfg.days - 6)), _far_city(u["home"], rng)) if rng.random() < 0.15 else None
        new_payees = 0
        alt_days = {int(x) for x in np.flatnonzero(rng.random(cfg.days) < 0.08)}  # whole days spent in the second city
        for d in days:
            ts = _hour_ts(math.floor(d), rng.normal(u["hour"], 2.5))
            day = (ts - T0) / DAY
            device, sim_h, scenario = u["device"], None, "routine"
            if phone_day is not None and day >= phone_day:
                device, scenario = f"d{u['i']}b", "new_phone" if day - phone_day < 7 else "routine"
                if phone_sim:
                    sim_h = (day - phone_day) * 24
            city = u["alt"] if math.floor(day) in alt_days else u["home"]
            if trip and trip[0] <= day < trip[0] + 3:
                city, scenario = trip[1], "travel"
            r = rng.random()
            if r < 0.65:
                payee, merchant = str(rng.choice(u["payees"])), False
            elif r < 0.90:
                payee, merchant = f"m{int(rng.integers(500))}", True
            else:
                new_payees += 1
                payee, merchant = f"n{u['i']}-{new_payees}", False
            amount = float(np.exp(rng.normal(u["mu"] - (0.6 if merchant else 0), u["sigma"])))
            if rng.random() < 0.03:
                amount *= rng.uniform(5, 20)
                payee, merchant, scenario = f"m{int(rng.integers(500, 900))}", True, "big_purchase"
            channel = "web" if u["web"] and rng.random() < 0.3 else "mobile"
            ip = u["vpn_ip"] if u["vpn"] and rng.random() < 0.5 else None
            profile = "distracted" if rng.random() < 0.1 else "normal"
            label = {"is_attack": False, "scenario": scenario if channel == "mobile" else "web", "attack_id": None, "difficulty": None}
            req(u, ts, device_id=device if channel == "mobile" else f"w{u['i']}", channel=channel, loc=_loc(city, rng), ip=ip,
                amount=amount, payee=payee, merchant=merchant, profile=profile, sim_h=sim_h,
                call=rng.random() < 0.03, share=rng.random() < 0.005, label=label,
                event_type="login" if channel == "web" and rng.random() < 0.3 else "payment")

    # ------------------------------------------------------------------ attacks on individual customers
    victims = rng.choice(len(users), int(cfg.attacked_frac * len(users)), replace=False)
    mix = np.array(ATTACK_MIX) / sum(ATTACK_MIX)
    for k, vi in enumerate(victims):
        u = users[int(vi)]
        scen = str(rng.choice(ATTACKS, p=mix))
        d = float(rng.uniform(0, 1))
        lab = {"is_attack": True, "scenario": scen, "attack_id": f"a{k}", "difficulty": round(d, 3)}
        start = _hour_ts(float(rng.uniform(4, cfg.days - 1)), rng.uniform(0, 24))
        if scen == "sim_swap" and rng.random() < 0.6:
            start = _hour_ts(math.floor((start - T0) / DAY), rng.uniform(0, 5))
        tries = int(rng.integers(1, 5))
        mule = f"mule{k}"
        base = math.exp(u["mu"])
        atk_city = str(rng.choice(FRAUD_HUBS)) if rng.random() < 1 - 0.7 * d else u["home"]
        atk_dev = f"atk{k}"
        for j in range(tries):
            ts = start + j * float(rng.uniform(120, 900))
            amount = min(base * float(rng.uniform(4, 25)) * (1 - 0.6 * d) + 500, 200000.0)
            common = dict(amount=amount, payee=mule if j == 0 or rng.random() < 0.7 else f"{mule}x{j}", label=lab)
            if scen == "ato_new_device":
                web = rng.random() < 0.4
                ipk = rng.random()
                ip = (_ip_in(str(rng.choice(DATACENTER)), rng) if ipk < 0.3 * (1 - d) else
                      _ip_in(str(rng.choice(ANONYMISER)), rng) if ipk < 0.5 * (1 - d) else _resid_ip(rng))
                req(u, ts, device_id=atk_dev, channel="web" if web else "mobile", loc=_loc(atk_city, rng), ip=ip,
                    profile="remote", emulator=rng.random() < 0.4 * (1 - d), rooted=rng.random() < 0.3 * (1 - d), **common)
            elif scen == "sim_swap":
                req(u, ts, device_id=atk_dev, loc=_loc(atk_city, rng), ip=_resid_ip(rng), profile="remote",
                    sim_h=float(rng.uniform(0.5, 30)), rooted=rng.random() < 0.2 * (1 - d), **common)
            elif scen == "remote_access":
                req(u, ts, device_id=u["device"], loc=_loc(u["home"], rng), ip=u["ips"][0], profile="remote",
                    remote_app=rng.random() < 1 - 0.6 * d, share=rng.random() < 0.7 * (1 - d),
                    call=rng.random() < 0.6 * (1 - d), **common)
            else:  # coerced
                req(u, ts, device_id=u["device"], loc=_loc(u["home"], rng), ip=u["ips"][0], profile="coerced",
                    call=rng.random() < 0.95 - 0.8 * d, share=rng.random() < 0.2 * (1 - d),
                    tts=float(rng.lognormal(math.log(45), 0.6)), **common)

    # ------------------------------------------------------------------ bot campaigns
    for c in range(cfg.bot_campaigns):
        d = float(rng.uniform(0, 1))
        lab = {"is_attack": True, "scenario": "bot", "attack_id": f"b{c}", "difficulty": round(d, 3)}
        start = _hour_ts(float(rng.uniform(2, cfg.days - 1)), rng.uniform(0, 24))
        targets = rng.choice(len(users), int(rng.integers(15, 50)), replace=False)
        rotate = rng.random() < d
        ipk = rng.random()
        ip_pool = [(_ip_in(str(rng.choice(DATACENTER)), rng) if ipk < 0.6 * (1 - d) + 0.1 else
                    _ip_in(str(rng.choice(ANONYMISER)), rng) if ipk < 0.8 * (1 - d) + 0.1 else _resid_ip(rng))
                   for _ in range(3 if not rotate else len(targets))]
        city = str(rng.choice(FRAUD_HUBS))
        for j, ti in enumerate(targets):
            u = users[int(ti)]
            ts = start + float(rng.uniform(0, 3600))
            human = rng.random() < d
            req(u, ts, device_id=f"bot{c}-{j}" if rotate else f"bot{c}", channel="web", loc=_loc(city, rng),
                ip=ip_pool[j % len(ip_pool)], amount=float(rng.uniform(1, 200)), payee=f"botmule{c}", label=lab,
                emulator=rng.random() < 0.8 * (1 - d), rooted=False, tts=float(rng.uniform(4, 15) if human else rng.uniform(0.3, 2.5)),
                inputs=int(rng.integers(5, 20) if human else rng.integers(0, 3)),
                event_type="login" if rng.random() < 0.4 else "payment")

    events.sort(key=lambda r: (r["ts"], r["event_id"]))
    _payee_risk(events, rng)
    return events


def _payee_risk(events: list[dict], rng):
    """Stand-in for payee intelligence (the payee-side model of the RAKSHAM layer): most mule accounts used in a fresh
    attack are new and unflagged (that model's cold-start AUC is 0.46), a minority are already flagged. Payee
    intelligence only knows some accounts: half of the unflagged payees (genuine or not) have no score (None)."""
    seen: dict[str, float | None] = {}
    for r in events:
        pid = r["transaction"].get("payee_id")
        if not pid:
            continue
        if pid not in seen:
            mule = pid.startswith(("mule", "botmule"))
            flagged = rng.random() < (0.30 if mule else 0.01)
            seen[pid] = (round(float(rng.uniform(0.5, 0.95)), 4) if flagged else
                         None if rng.random() < 0.5 else round(float(rng.uniform(0.0, 0.15)), 4))
        r["transaction"]["payee_risk"] = seen[pid]


# ---------------------------------------------------------------------------- touch scores
def attach_bio(events: list[dict], bank=None, scorer=None, seed: int = 7) -> str:
    """Fill behaviour.bio_dev for every mobile request with a touch window. Returns how: 'hmog' (real gestures scored
    by the real model) or 'quantiles' (draws from the saved measured distributions)."""
    idx = [i for i, r in enumerate(events) if r.get("bio_profile")]
    if bank is not None and scorer is not None:
        from ml.sim.hmog_bank import seeded_rng
        for s in bank.subjects:
            if str(s) not in scorer.profiles:
                scorer.enroll(str(s), bank.enrolment(s))
        x = np.stack([bank.resolve_array(bank.window_ref(events[i]["bio_subject"], events[i]["bio_profile"], 1.0,
                                                         seeded_rng("auth", seed, events[i]["event_id"]))) for i in idx])
        dev = scorer.deviation_arrays([str(events[i]["bio_subject"]) for i in idx], x)
        how = "hmog"
    else:
        q = json.loads(BIO_QUANTILES.read_text())
        rng = np.random.default_rng(seed)
        dev = np.array([np.interp(rng.random(), np.linspace(0, 1, len(q[events[i]["bio_profile"]])),
                                  q[events[i]["bio_profile"]]) for i in idx])
        how = "quantiles"
    for i, v in zip(idx, dev):
        events[i]["behaviour"]["bio_dev"] = round(float(v), 4)
    return how


TYPING_QUANTILES = Path("ml/auth/artifacts/typing_quantiles.json")
BOT_TIMINGS = (0.06, 0.09, 0.03)   # scripted typing: constant hold / down-down / up-down (seconds)


def attach_typing(events: list[dict], scorer=None, seed: int = 7) -> str:
    """Fill behaviour.typing_dev for every request with a typed attempt (CMU keystroke data, held-out test subjects).
    normal = the owner's own later-session attempt; remote = another subject's attempt; coerced = the owner's attempt
    typed slower and more hesitantly (latencies x1.3-1.8, holds x1.1: an assumption, CMU has no coercion labels);
    bot = scripted constant timings. Without the data / model, deviations come from the saved measured quantiles."""
    idx = [i for i, r in enumerate(events) if r.get("typing_profile")]
    rng = np.random.default_rng(seed + 2)
    if scorer is not None:
        from ml.models.keystroke.data import load_cmu, timings
        df = load_cmu()
        raw = timings(df)
        subjects = scorer.meta["split"]["test"]
        for s in subjects:
            if str(s) not in scorer.profiles:
                scorer.enroll(str(s), raw[((df["user"] == s) & (df["session"] <= 4)).to_numpy()])
        probes = {s: raw[((df["user"] == s) & (df["session"] >= 5)).to_numpy()] for s in subjects}
        owners, x = [], np.zeros((len(idx), raw.shape[1]), dtype="float32")
        for k, i in enumerate(idx):
            r = events[i]
            own = subjects[r["typing_owner"] % len(subjects)]
            prof = r["typing_profile"]
            if prof == "bot":
                h, dd, ud = BOT_TIMINGS
                x[k] = np.r_[np.tile([h, dd, ud], 10), h] * np.exp(rng.normal(0, 0.02, raw.shape[1]))
            else:
                src = own if prof != "remote" else int(rng.choice([s for s in subjects if s != own]))
                x[k] = probes[src][int(rng.integers(len(probes[src])))]
                if prof == "coerced":
                    lat = np.r_[np.tile([False, True, True], 10), False]
                    x[k] = np.where(lat, x[k] * rng.uniform(1.3, 1.8), x[k] * 1.1)
            owners.append(str(own))
        dev = scorer.deviation_many(owners, x)
        how = "cmu"
    else:
        q = json.loads(TYPING_QUANTILES.read_text())
        dev = np.array([np.interp(rng.random(), np.linspace(0, 1, len(q[events[i]["typing_profile"]])),
                                  q[events[i]["typing_profile"]]) for i in idx])
        how = "quantiles"
    for i, v in zip(idx, dev):
        events[i]["behaviour"]["typing_dev"] = round(float(v), 4)
    return how


def save_typing_quantiles(events: list[dict], path: Path = TYPING_QUANTILES):
    out = {}
    for prof in ("normal", "coerced", "remote", "bot"):
        v = np.array([r["behaviour"]["typing_dev"] for r in events if r.get("typing_profile") == prof
                      and "typing_dev" in r["behaviour"]])
        if len(v):
            out[prof] = [round(float(x), 4) for x in np.quantile(v, np.linspace(0, 1, 101))]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))


def save_bio_quantiles(events: list[dict], path: Path = BIO_QUANTILES):
    out = {}
    for prof in ("normal", "distracted", "coerced", "remote"):
        v = np.array([r["behaviour"]["bio_dev"] for r in events if r.get("bio_profile") == prof and "bio_dev" in r["behaviour"]])
        if len(v):
            out[prof] = [round(float(x), 4) for x in np.quantile(v, np.linspace(0, 1, 101))]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
