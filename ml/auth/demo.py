"""Demo customer and scenarios for the console and the pitch.

One demo customer (Asha, Ludhiana) with 30 days of ordinary history and a touch profile enrolled from a held-out HMOG
subject. Each scenario builds a real /v1/authenticate request on top of that history; the touch windows are real HMOG
gestures (own hands, own hands under stress, someone else's hands) from a small packed file, so a container can verify
touch live without the 6 GB dataset.

    python -m ml.auth.demo        # (re)build ml/auth/artifacts/demo_gestures.json from the HMOG cache
"""
from __future__ import annotations

import json
import math
import time
import zlib
from pathlib import Path

import numpy as np

from .geo import ALL_PLACES
from .state import AuthState, new_user

PACK = Path("ml/auth/artifacts/demo_gestures.json")
USER = "demo-asha"
HOME, DEVICE, IP = "Ludhiana", "asha-pixel-7", "49.36.112.45"
PAYEES = ["kirana-sharma", "milk-dairy", "electricity-pspcl", "brother-raj", "pharmacy-apollo", "mobile-recharge"]

SCENARIOS = {
    "genuine_routine": ("Genuine: everyday payment", "Asha pays her usual grocer ₹640 from her own phone at home.", False),
    "genuine_big_purchase": ("Genuine: big purchase", "Asha buys a ₹18,500 refrigerator from a new merchant, own phone, own hands.", False),
    "genuine_new_phone": ("Genuine: new phone + new SIM", "Asha switched to a new phone and SIM this morning; pays her brother ₹1,500.", False),
    "genuine_travel": ("Genuine: travelling", "Asha is in Delhi for a wedding and pays ₹900 from her own phone.", False),
    "ato_new_device": ("Attack: stolen credentials", "Phished credentials used on an emulator through a hosting-provider IP, "
                       "₹45,000 to a mule account already flagged by payee intelligence.", True),
    "sim_swap": ("Attack: SIM swap", "Asha's number was ported to the attacker's SIM 3 hours ago; a new phone in Kolkata "
                 "tries ₹60,000 to a new payee.", True),
    "bot": ("Attack: credential stuffing", "A scripted login from a device and IP that touched 30 other accounts in the last hour.", True),
    "remote_access": ("Attack: remote-access takeover", "A 'support agent' installed a remote-control app on Asha's phone and "
                      "is driving it: own device, someone else's hands, ₹30,000 to a mule.", True),
    "coerced": ("Attack: coached victim", "A caller posing as police keeps Asha on the line while she pays ₹95,000 herself.", True),
}


# ---------------------------------------------------------------------------- gesture pack
def build_pack(path: Path = PACK, n_windows: int = 24) -> dict:
    from ml.sim.hmog_bank import HmogBank, seeded_rng
    bank = HmogBank.load()
    if bank is None:
        raise FileNotFoundError("HMOG gesture cache not found (python -m ml.models.biometrics.data)")
    subject = bank.subjects[0]
    pack = {"subject": int(subject), "enrolment": bank.enrolment(subject), "windows": {}}
    for prof in ("normal", "coerced", "remote"):
        pack["windows"][prof] = [bank.resolve(bank.window_ref(subject, prof, 1.0, seeded_rng("demo", prof, k)))[1]
                                 for k in range(n_windows)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, separators=(",", ":")))
    return pack


class DemoWorld:
    def __init__(self, path: Path = PACK):
        self.pack = json.loads(path.read_text()) if path.exists() else None

    def gestures(self, profile: str, rng) -> list[dict] | None:
        if not self.pack:
            return None
        w = self.pack["windows"][profile]
        return w[int(rng.integers(len(w)))]

    def seed(self, state: AuthState, bio=None, now: float | None = None, seed: int = 0):
        """Reset the demo customer to 30 days of ordinary history ending 6 hours ago; enrol her touch profile."""
        now = time.time() if now is None else now
        rng = np.random.default_rng(seed)
        state.kv.set(f"user:{USER}", new_user(now - 31 * 86400))
        for k in ("device:bot-farm-7", "ip:34.93.10.77", f"device:{DEVICE}", "device:asha-new-phone", "device:atk-emu-1",
                  "device:atk-phone-2"):
            state.kv.delete(k)
        # her usual hours are centred on the current IST hour, so a demo run at any time of day is not "unusual hour"
        days = np.floor(rng.uniform(1, 31, 46))
        times = [now - d * 86400 + rng.normal(0, 1.5) * 3600 for d in days]
        for i, ts in enumerate(sorted(min(float(t), now - 6 * 3600) for t in times)):
            req = {"user_id": USER, "ts": ts, "device": {"device_id": DEVICE},
                   "network": {"ip": IP, **_loc(HOME, rng)},
                   "transaction": {"amount": float(np.exp(rng.normal(math.log(700), 0.6))), "payee_id": PAYEES[i % len(PAYEES)]}}
            state.commit(USER, req, ts)
        if bio is not None and self.pack and USER not in bio.profiles:
            bio.enroll(USER, self.pack["enrolment"])

    def request(self, scenario: str, now: float | None = None) -> dict:
        if scenario not in SCENARIOS:
            raise KeyError(scenario)
        now = time.time() if now is None else now
        rng = np.random.default_rng(zlib.crc32(scenario.encode()))  # same touch window every run: repeatable demo
        r = {"user_id": USER, "ts": now, "channel": "mobile", "event_type": "payment",
             "device": {"device_id": DEVICE, "platform": "android", "is_emulator": False, "is_rooted": False,
                        "remote_access_app": False, "screen_share_active": False, "sim_change_hours": None},
             "network": {"ip": IP, **_loc(HOME, rng)},
             "behaviour": {"gestures": self.gestures("normal", rng), "time_to_submit_s": 16.0, "input_events": 34,
                           "unknown_call_active": False},
             "transaction": {"amount": 640.0, "payee_id": "kirana-sharma", "payee_is_merchant": True}}
        d, net, beh, tx = r["device"], r["network"], r["behaviour"], r["transaction"]
        if scenario == "genuine_big_purchase":
            tx.update(amount=18500.0, payee_id="croma-ludhiana", payee_is_merchant=True)
            beh["time_to_submit_s"] = 41.0
        elif scenario == "genuine_new_phone":
            d.update(device_id="asha-new-phone", sim_change_hours=5.0)
            tx.update(amount=1500.0, payee_id="brother-raj", payee_is_merchant=False)
        elif scenario == "genuine_travel":
            net.update(ip="106.211.40.12", **_loc("Delhi", rng))
            tx.update(amount=900.0, payee_id="m-delhi-caterer", payee_is_merchant=True)
        elif scenario == "ato_new_device":
            d.update(device_id="atk-emu-1", is_emulator=True)
            net.update(ip="34.93.10.77", **_loc("Jamtara", rng))
            beh.update(gestures=self.gestures("remote", rng), time_to_submit_s=9.0, input_events=12)
            tx.update(amount=45000.0, payee_id="mule-8812", payee_is_merchant=False, payee_risk=0.78)
        elif scenario == "sim_swap":
            d.update(device_id="atk-phone-2", sim_change_hours=3.0)
            net.update(ip="117.201.4.9", **_loc("Kolkata", rng))
            beh.update(gestures=self.gestures("remote", rng), time_to_submit_s=12.0)
            tx.update(amount=60000.0, payee_id="mule-4410", payee_is_merchant=False)
        elif scenario == "bot":
            r.update(channel="web", event_type="login")
            d.update(device_id="bot-farm-7", platform="web", is_emulator=True)
            net.update(ip="34.93.10.77", **_loc("Jamtara", rng))
            beh.update(gestures=None, time_to_submit_s=0.8, input_events=1)
            tx.update(amount=0.0, payee_id=None)
        elif scenario == "remote_access":
            d.update(remote_access_app=True, screen_share_active=True)
            beh.update(gestures=self.gestures("remote", rng), unknown_call_active=True, time_to_submit_s=22.0)
            tx.update(amount=30000.0, payee_id="mule-7781", payee_is_merchant=False)
        elif scenario == "coerced":
            beh.update(gestures=self.gestures("coerced", rng), unknown_call_active=True, time_to_submit_s=74.0)
            tx.update(amount=95000.0, payee_id="cbi-settlement-acct", payee_is_merchant=False)
        return r

    def prepare(self, scenario: str, state: AuthState, now: float | None = None):
        """Scenario-specific state (the bot's device and IP have touched many accounts in the last hour)."""
        if scenario == "bot":
            now = time.time() if now is None else now
            for i in range(30):
                state.record_attempt(f"victim-{i:03d}", "bot-farm-7", "34.93.10.77", now - 3000 + i * 90)


def _loc(city: str, rng) -> dict:
    lat, lon = ALL_PLACES[city]
    return {"city": city, "lat": round(lat + rng.normal(0, 0.01), 4), "lon": round(lon + rng.normal(0, 0.01), 4)}


if __name__ == "__main__":
    p = build_pack()
    print(f"demo pack: subject {p['subject']}, {len(p['enrolment'])} enrolment gestures, "
          f"{ {k: len(v) for k, v in p['windows'].items()} } windows -> {PACK} ({PACK.stat().st_size / 1024:.0f} KB)")
