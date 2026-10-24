"""Golden vectors for the client SDKs, computed with the training pipeline's own code.

The SDKs extract touch-gesture features and keystroke timings on the device, and sign requests. Each SDK's tests
replay the raw inputs below and must reproduce these outputs, so what a phone or browser sends is exactly what the
models were trained on (ml/models/biometrics/data.py, ml/models/keystroke/data.py) and what the gateway checks
(backend/security.py).

    python sdk/spec/make_golden.py          # -> sdk/spec/golden.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from backend.security import sign  # noqa: E402
from ml.models.biometrics.data import (FEATURES, POST_MS, PRE_MS, SCREEN_H, SCREEN_W, SENSOR_COLS, TOUCH_COLS,  # noqa: E402
                                       add_motion_features, extract_gestures)
from ml.models.keystroke.data import COLUMNS, KEYS  # noqa: E402

OUT = Path(__file__).with_name("golden.json")
DOWN, UP, MOVE = 0, 1, 2


# ---------------------------------------------------------------------------- touch
def touch_frames() -> list[dict]:
    """Raw single-pointer frames (HMOG layout): taps, swipes, a long press, and the cases the pipeline drops."""
    frames: list[dict] = []

    def add(t, action, x, y, size=0.022, count=1, orientation=0):
        frames.append({"t": t, "action": action, "x": x, "y": y, "size": size, "pointer_count": count,
                       "orientation": orientation})

    # 1. tap
    add(1000, DOWN, 540, 1200, 0.021); add(1030, MOVE, 542, 1203, 0.023); add(1080, UP, 543, 1204, 0.022)
    # 2. upward swipe, 16 ms frames
    for i in range(17):
        add(2000 + 16 * i, DOWN if i == 0 else UP if i == 16 else MOVE, 300 + 2 * i, 1500 - 37.5 * i, 0.02 + 0.0004 * i)
    # 3. long press with jitter
    add(4000, DOWN, 800, 400, 0.024)
    for i in range(1, 12):
        add(4000 + 60 * i, MOVE, 800 + (i % 3), 400 - (i % 2), 0.025)
    add(4700, UP, 801, 401, 0.025)
    # 4. held 5.5 s: dropped (duration >= 5 s)
    add(6000, DOWN, 100, 100); add(9000, MOVE, 110, 105); add(11500, UP, 112, 106)
    # 5. a second finger lands mid-gesture: dropped (multi-touch)
    add(12000, DOWN, 500, 900); add(12050, MOVE, 520, 910, count=2); add(12100, UP, 530, 915)
    # 6. sideways swipe in landscape
    for i in range(9):
        add(13000 + 12 * i, DOWN if i == 0 else UP if i == 8 else MOVE, 200 + 60 * i, 700 + 3 * i, 0.019, orientation=1)
    # 7. after a minute of nothing: gap is clipped to 60 s; no sensor data here
    add(80000, DOWN, 1000, 1800, 0.03); add(80040, MOVE, 990, 1790, 0.031); add(80090, UP, 985, 1785, 0.03)
    # 8. finger still down when the stream ends: dropped (never lifted)
    add(90000, DOWN, 400, 400); add(90050, MOVE, 420, 420)
    return frames


def motion(kind: str) -> list[dict]:
    """Accelerometer (m/s^2, with gravity) / gyroscope (rad/s) at 100 Hz from 0.9 s to 15 s."""
    out = []
    for t in range(900, 15000, 10):
        if kind == "acc":
            out.append({"t": t, "x": 0.3 * math.sin(t / 50), "y": 0.2 * math.cos(t / 70), "z": 9.7 + 0.1 * math.sin(t / 30)})
        else:
            out.append({"t": t, "x": 0.05 * math.sin(t / 40), "y": 0.3 * math.cos(t / 90), "z": 0.02 * math.sin(t / 20)})
    return out


def gesture_features(frames: list[dict], acc: list[dict], gyr: list[dict]) -> list[dict]:
    touch = pd.DataFrame([{"systime": f["t"], "event_time": f["t"], "activity_id": 1, "pointer_count": f["pointer_count"],
                           "pointer_id": 0, "action_id": f["action"], "x": f["x"], "y": f["y"], "pressure": 1.0,
                           "size": f["size"], "orientation": f["orientation"]} for f in frames], columns=TOUCH_COLS)
    g = extract_gestures(touch)

    def sensor(rows):
        return pd.DataFrame([{"systime": r["t"], "event_time": r["t"], "activity_id": 1, "x": r["x"], "y": r["y"],
                              "z": r["z"], "orientation": 0} for r in rows], columns=SENSOR_COLS)

    g = add_motion_features(g, sensor(acc), "acc")
    g = add_motion_features(g, sensor(gyr), "gyr")
    return [{k: (None if pd.isna(v) else float(v)) for k, v in row.items()} for row in g[FEATURES].to_dict("records")]


# ---------------------------------------------------------------------------- keystrokes
def key_events() -> tuple[list[dict], list[dict]]:
    """One attempt at the CMU password `.tie5Roanl` + Return as raw key events (ms), with rollover (the next key goes
    down before the previous comes up), a Shift held for the `R`, and an auto-repeat event; plus the per-key
    down/up times the SDK should recover from them."""
    keys = [  # (code, down, up)
        ("Period", 0, 95), ("KeyT", 230, 330), ("KeyI", 410, 480), ("KeyE", 470, 560), ("Digit5", 700, 790),
        ("KeyR", 1010, 1100), ("KeyO", 1180, 1250), ("KeyA", 1300, 1390), ("KeyN", 1380, 1460), ("KeyL", 1530, 1610),
        ("Enter", 1800, 1890),
    ]
    events = [{"code": c, "type": "down", "t": d} for c, d, _ in keys] + [{"code": c, "type": "up", "t": u} for c, _, u in keys]
    events += [{"code": "ShiftRight", "type": "down", "t": 950, "modifier": True},
               {"code": "ShiftRight", "type": "up", "t": 1120, "modifier": True},
               {"code": "KeyL", "type": "down", "t": 1580, "repeat": True}]
    events.sort(key=lambda e: (e["t"], e["type"] == "up"))
    return events, [{"code": c, "down": d, "up": u} for c, d, u in keys]


def timings(keys: list[dict]) -> list[float]:
    """31 timings in seconds, in ml.models.keystroke.data.COLUMNS order."""
    names, vals = [], []
    for i, (a, b) in enumerate(zip(KEYS, KEYS[1:])):
        ka, kb = keys[i], keys[i + 1]
        names += [f"H.{a}", f"DD.{a}.{b}", f"UD.{a}.{b}"]
        vals += [(ka["up"] - ka["down"]) / 1000, (kb["down"] - ka["down"]) / 1000, (kb["down"] - ka["up"]) / 1000]
    names.append(f"H.{KEYS[-1]}")
    vals.append((keys[-1]["up"] - keys[-1]["down"]) / 1000)
    assert names == COLUMNS, "layout drifted from ml.models.keystroke.data.COLUMNS"
    return [round(v, 6) for v in vals]


# ---------------------------------------------------------------------------- signing
def signing() -> dict:
    secret, ts = "pramaan-test-secret", 1700000000
    body = json.dumps({"user_id": "demo-asha", "channel": "mobile", "device": {"device_id": "asha-pixel-7"},
                       "network": {"city": "लुधियाना"}, "transaction": {"amount": 640.0, "payee_id": "kirana-sharma"}},
                      ensure_ascii=False, separators=(",", ":"))
    return {"secret": secret, "timestamp": ts, "body": body, "headers": sign(secret, body.encode("utf-8"), ts)}


def main():
    frames, acc, gyr = touch_frames(), motion("acc"), motion("gyr")
    events, keys = key_events()
    golden = {
        "about": "Generated by sdk/spec/make_golden.py from the training pipeline's own code. Do not edit by hand.",
        "touch": {"screen": {"width": SCREEN_W, "height": SCREEN_H}, "pre_ms": PRE_MS, "post_ms": POST_MS,
                  "feature_names": FEATURES, "frames": frames, "acc": acc, "gyr": gyr,
                  "features": gesture_features(frames, acc, gyr)},
        "keystrokes": {"password": ".tie5Roanl", "keys": KEYS, "columns": COLUMNS, "events": events, "per_key": keys,
                       "timings": timings(keys)},
        "signing": signing(),
    }
    OUT.write_text(json.dumps(golden, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(golden["touch"]["features"])
    print(f"-> {OUT.relative_to(ROOT)}: {n} gestures kept of 8, {len(golden['keystrokes']['timings'])} timings, signature ok")


if __name__ == "__main__":
    main()
