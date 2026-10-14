"""Live authentication state: what the service remembers about users, devices and IP addresses.

Stored as one small JSON document per key in a key-value store: in-memory for tests, the simulator and a single
instance; Redis (Memorystore on Google Cloud) when REDIS_URL is set, so every Cloud Run instance shares the same state.

    user:{id}    devices (first/last seen, uses, trusted), last location, cities, amount statistics (log scale,
                 Welford), payees, hour-of-day histogram, last-24h payments, failed challenges
    device:{id}  accounts seen on this device in the last 30 days
    ip:{addr}    accounts that used this address in the last hour
    pending:{id} a challenged decision waiting for /v1/challenge/verify (15-minute TTL)

Reads happen before a decision (features are causal); history is updated only when a transaction completes
(allowed, or its challenge passed), so a blocked attacker never becomes part of the victim's "normal".
"""
from __future__ import annotations

import copy
import json
import math
import os
import threading

DAY = 86400.0
TRUST_AFTER_DAYS = 7.0      # a device becomes trusted after this long in use ...
TRUST_AFTER_USES = 3        # ... with at least this many completed transactions (or after a strong challenge)
MAX_PAYEES = 300


class MemoryKV:
    def __init__(self):
        self.d: dict[str, dict] = {}
        self.lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        v = self.d.get(key)
        return copy.deepcopy(v) if v is not None else None

    def set(self, key: str, value: dict, ttl: int | None = None):
        with self.lock:
            self.d[key] = copy.deepcopy(value)

    def delete(self, key: str):
        self.d.pop(key, None)

    def clear(self):
        self.d.clear()

    def snapshot(self) -> "MemoryKV":
        kv = MemoryKV()
        kv.d = copy.deepcopy(self.d)
        return kv

    @property
    def backend(self) -> str:
        return "memory"


class RedisKV:
    def __init__(self, url: str, prefix: str = "bios:"):
        import redis  # optional dependency
        self.r = redis.Redis.from_url(url, socket_timeout=0.5)
        self.r.ping()
        self.prefix = prefix

    def get(self, key: str) -> dict | None:
        v = self.r.get(self.prefix + key)
        return json.loads(v) if v else None

    def set(self, key: str, value: dict, ttl: int | None = None):
        self.r.set(self.prefix + key, json.dumps(value, separators=(",", ":")), ex=ttl)

    def delete(self, key: str):
        self.r.delete(self.prefix + key)

    def clear(self):
        for k in self.r.scan_iter(self.prefix + "*"):
            self.r.delete(k)

    @property
    def backend(self) -> str:
        return "redis"


def make_kv():
    url = os.environ.get("REDIS_URL")
    return RedisKV(url) if url else MemoryKV()


# ---------------------------------------------------------------------------- documents
def new_user(now: float) -> dict:
    return {"devices": {}, "geo": None, "cities": {}, "amt": [0, 0.0, 0.0], "payees": {}, "hours": [0] * 24,
            "recent": [], "fails": [], "n": 0, "first": now}


def device_trusted(dev: dict, now: float) -> bool:
    return bool(dev.get("trusted")) or (now - dev["first"] >= TRUST_AFTER_DAYS * DAY and dev["n"] >= TRUST_AFTER_USES)


class AuthState:
    def __init__(self, kv=None):
        self.kv = kv if kv is not None else make_kv()

    # -------------------------------------------------------------- reads
    def user(self, uid: str, now: float) -> dict:
        return self.kv.get(f"user:{uid}") or new_user(now)

    def device_accounts(self, device_id: str, now: float) -> dict:
        d = self.kv.get(f"device:{device_id}") or {"users": {}}
        return {u: t for u, t in d["users"].items() if now - t <= 30 * DAY}

    def ip_accounts(self, ip: str, now: float) -> dict:
        d = self.kv.get(f"ip:{ip}") or {"users": {}}
        return {u: t for u, t in d["users"].items() if now - t <= 3600}

    # -------------------------------------------------------------- writes
    def record_attempt(self, uid: str, device_id: str | None, ip: str | None, now: float):
        """Every attempt, completed or not: which accounts each device / IP touches (credential stuffing, device farms)."""
        if device_id:
            users = self.device_accounts(device_id, now)
            users[uid] = now
            self.kv.set(f"device:{device_id}", {"users": users}, ttl=int(30 * DAY))
        if ip:
            users = self.ip_accounts(ip, now)
            users[uid] = now
            self.kv.set(f"ip:{ip}", {"users": users}, ttl=3600)

    def commit(self, uid: str, req: dict, now: float, trust_device: bool = False):
        """A completed transaction becomes part of the user's history."""
        u = self.user(uid, now)
        dev_id = (req.get("device") or {}).get("device_id")
        if dev_id:
            d = u["devices"].get(dev_id) or {"first": now, "last": now, "n": 0, "trusted": False}
            d["last"], d["n"] = now, d["n"] + 1
            d["trusted"] = bool(d.get("trusted") or trust_device)
            u["devices"][dev_id] = d
        net = req.get("network") or {}
        if net.get("lat") is not None and net.get("lon") is not None:
            u["geo"] = [net["lat"], net["lon"], now]
        if net.get("city"):
            u["cities"][net["city"]] = u["cities"].get(net["city"], 0) + 1
        tx = req.get("transaction") or {}
        amount = float(tx.get("amount") or 0)
        if amount > 0:
            x = math.log1p(amount)
            n, mean, m2 = u["amt"]
            n += 1
            delta = x - mean
            mean += delta / n
            m2 += delta * (x - mean)
            u["amt"] = [n, mean, m2]
            u["recent"] = [r for r in u["recent"] if now - r[0] <= DAY] + [[now, amount]]
            pid = tx.get("payee_id")
            if pid:
                u["payees"][pid] = u["payees"].get(pid, 0) + 1
                if len(u["payees"]) > MAX_PAYEES:  # forget the rarest payees
                    for k, _ in sorted(u["payees"].items(), key=lambda kv: kv[1])[: len(u["payees"]) - MAX_PAYEES]:
                        del u["payees"][k]
        u["hours"][_hour(now)] += 1
        u["n"] += 1
        self.kv.set(f"user:{uid}", u)

    def trust_device(self, uid: str, device_id: str, now: float):
        u = self.user(uid, now)
        d = u["devices"].get(device_id) or {"first": now, "last": now, "n": 0, "trusted": False}
        d["trusted"] = True
        u["devices"][device_id] = d
        self.kv.set(f"user:{uid}", u)

    def record_failure(self, uid: str, now: float):
        u = self.user(uid, now)
        u["fails"] = [t for t in u["fails"] if now - t <= DAY] + [now]
        self.kv.set(f"user:{uid}", u)

    # -------------------------------------------------------------- pending challenges
    def put_pending(self, decision_id: str, doc: dict):
        self.kv.set(f"pending:{decision_id}", doc, ttl=900)

    def pop_pending(self, decision_id: str) -> dict | None:
        doc = self.kv.get(f"pending:{decision_id}")
        if doc is not None:
            self.kv.delete(f"pending:{decision_id}")
        return doc


def _hour(ts: float) -> int:
    """Hour of day in India Standard Time (UTC+5:30)."""
    return int(((ts + 19800) % DAY) // 3600)
