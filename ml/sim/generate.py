"""Generate synthetic UPI sessions (scam workflows + benign look-alikes).

    python -m ml.sim.generate --n-sessions 10000 --scam-rate 0.2 --seed 7 --out data/sim
    python -m ml.sim.generate --demo digital_arrest --out data/sim/demo
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .builder import SessionBuilder
from .entities import AGE_GROUPS, World
from .schema import BENIGN_TYPOLOGIES, EVENT_COLUMNS, SCAM_TYPOLOGIES, SESSION_COLUMNS
from .typologies import TYPOLOGY_FNS, background

START = pd.Timestamp("2026-01-01")
WINDOW_DAYS = 90

# Scam mix at the start vs. end of the window — voice-clone scams are the "emerging" pattern.
SCAM_MIX_START = {"digital_arrest": 0.35, "fake_kyc_apk": 0.32, "investment_task": 0.23, "voice_clone_relative": 0.10}
SCAM_MIX_END = {"digital_arrest": 0.30, "fake_kyc_apk": 0.22, "investment_task": 0.18, "voice_clone_relative": 0.30}
BENIGN_MIX = {"routine": 0.37, "family_transfer": 0.13, "new_payee_service": 0.13,
              "large_new_payee": 0.08, "urgent_bill": 0.08, "support_install": 0.04,
              # hard negatives: legitimate look-alikes of each scam workflow
              "hospital_emergency": 0.04, "bank_app_update": 0.05, "legit_investing": 0.04,
              "genuine_urgent_family": 0.04}

# Who each typology targets (weights per AGE_GROUPS: 18-25, 26-40, 41-60, 60+)
AGE_TARGETING = {
    "digital_arrest": [0.5, 1.0, 2.5, 4.0],
    "voice_clone_relative": [0.3, 0.8, 2.5, 4.0],
    "investment_task": [3.0, 3.0, 1.2, 0.5],
}

BOOL_COLS = ["call_active", "call_video", "caller_reported", "screen_share_active", "sideloaded_app_present",
             "accessibility_granted", "sms_has_link", "payee_is_merchant", "payee_is_new"]
FLOAT_COLS = ["ts", "call_elapsed_s", "payee_vpa_age_days", "payee_mule_score", "amount",
              "bio_pressure", "bio_swipe_velocity", "bio_tap_interval_ms", "bio_hesitation_ms", "bio_orientation_var",
              "bio_model_dev"]


def _pick_typology(rng: np.random.Generator, is_scam: bool, frac: float) -> str:
    if is_scam:
        mix = {k: (1 - frac) * SCAM_MIX_START[k] + frac * SCAM_MIX_END[k] for k in SCAM_TYPOLOGIES}
    else:
        mix = BENIGN_MIX
    keys = list(mix)
    p = np.array([mix[k] for k in keys])
    return str(rng.choice(keys, p=p / p.sum()))


def _user_sampler(world: World):
    """Pre-compute per-typology user sampling probabilities."""
    ages = np.array([u.age_group for u in world.users])
    probs = {}
    for typ, w in AGE_TARGETING.items():
        weights = np.array([w[AGE_GROUPS.index(a)] for a in ages], dtype=float)
        probs[typ] = weights / weights.sum()
    return probs


BACKGROUND_SCALE = {"benign": 1.0, "scam": 0.3}  # scam victims also have normal activity before contact


def run_session(world: World, rng: np.random.Generator, session_id: str, typology: str,
                start_time: pd.Timestamp, difficulty: float, user=None, background_scale: float | None = None,
                adversary: dict | None = None):
    if user is None:
        user = world.users[int(rng.integers(len(world.users)))]
    is_scam = typology in SCAM_TYPOLOGIES
    b = SessionBuilder(session_id, user, world, rng, difficulty, is_scam=is_scam, adversary=adversary)
    scale = BACKGROUND_SCALE["scam" if is_scam else "benign"] if background_scale is None else background_scale
    world_rng, world.rng = world.rng, rng  # payee / mule sampling inside the session uses the session's stream
    try:
        if scale > 0:
            background(b, scale)  # Stage.NONE: activity before any scam contact
        TYPOLOGY_FNS[typology](b)
    finally:
        world.rng = world_rng
    for r in b.rows:
        r["event_time"] = start_time + pd.to_timedelta(r["ts"], unit="s")
    meta = {
        "session_id": session_id, "user_id": user.user_id, "typology": typology, "is_scam": is_scam,
        "start_time": start_time, "n_events": len(b.rows),
        "extraction_ts": b.extraction_ts if is_scam else None,
        "loss_amount": round(b.loss, 2) if is_scam else 0.0, "difficulty": round(difficulty, 3),
    }
    return b.rows, meta


def _to_frames(rows: list[dict], metas: list[dict]):
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    for c in BOOL_COLS:
        events[c] = events[c].astype("boolean")
    for c in FLOAT_COLS:
        events[c] = events[c].astype("float64")
    events["event_time"] = pd.to_datetime(events["event_time"])
    sessions = pd.DataFrame(metas, columns=SESSION_COLUMNS)
    sessions["extraction_ts"] = sessions["extraction_ts"].astype("float64")
    return events, sessions


def generate(n_sessions: int = 10_000, scam_rate: float = 0.2, seed: int = 7, adversary: dict | None = None):
    """`adversary`: adaptive-scammer knobs applied to every scam session (ml/sim/builder.py ADVERSARY_KNOBS)."""
    rng = np.random.default_rng(seed)
    n_scam = int(round(n_sessions * scam_rate))
    world = World(
        rng,
        n_users=max(500, n_sessions // 4),
        n_merchants=max(200, n_sessions // 20),
        n_personal=max(1500, (n_sessions // 4) * 3),
        n_mules=max(50, int(n_scam * 0.3)),
    )
    user_probs = _user_sampler(world)

    start_offsets = np.sort(rng.uniform(0, WINDOW_DAYS * 86400, n_sessions))
    scam_flags = np.zeros(n_sessions, dtype=bool)
    scam_flags[rng.choice(n_sessions, n_scam, replace=False)] = True

    # Pass 1 fixes who, what and how hard for every session; pass 2 plays each session on its own random stream.
    # So a session's events never depend on how many draws earlier sessions used: an adaptive-scammer world
    # (ml/engine/robustness.py) has exactly the same genuine sessions, scam typologies and victims as the baseline.
    plan = []
    for i in range(n_sessions):
        frac = start_offsets[i] / (WINDOW_DAYS * 86400)
        typ = _pick_typology(rng, bool(scam_flags[i]), frac)
        p = user_probs.get(typ)
        user = world.users[int(rng.choice(len(world.users), p=p))] if p is not None else world.users[int(rng.integers(len(world.users)))]
        difficulty = float(rng.beta(2, 2)) if scam_flags[i] else 0.0
        plan.append((typ, user, difficulty))
    rows, metas = [], []
    for i, (typ, user, difficulty) in enumerate(plan):
        r, m = run_session(world, np.random.default_rng([seed, i]), f"S{i:07d}", typ,
                           START + pd.to_timedelta(start_offsets[i], unit="s"), difficulty, user, adversary=adversary)
        rows.extend(r)
        metas.append(m)

    events, sessions = _to_frames(rows, metas)
    return events, sessions, world.users_frame(), world.payees


DEMO_PERSONAS = ("senior", "student", "professional")


def _demo_user(world: World, persona: str):
    """senior: first 41+ user (the default demo customer); student: the lowest-spending 18-25 user;
    professional: the highest-spending 26-40 user."""
    def pick(groups, key=None):
        us = [u for u in world.users if u.age_group in groups]
        if not us:
            return world.users[0]
        return us[0] if key is None else key(us, key=lambda u: u.avg_txn_amount)
    if persona == "senior":
        return pick(("41-60", "60+"))
    if persona == "student":
        return pick(("18-25",), min)
    if persona == "professional":
        return pick(("26-40",), max)
    raise KeyError(persona)


def generate_demo(typology: str, seed: int = 2026, persona: str = "senior"):
    """One clean (difficulty=0), reproducible session for the live demo, for one of DEMO_PERSONAS."""
    rng = np.random.default_rng(seed)
    world = World(rng, n_users=50, n_merchants=50, n_personal=300, n_mules=20)
    user = _demo_user(world, persona)
    rows, meta = run_session(world, rng, f"DEMO_{typology}", typology, pd.Timestamp("2026-03-15 11:00"), 0.0, user,
                             background_scale=0.0)
    events, sessions = _to_frames(rows, [meta])
    return events, sessions, world.users_frame(), world.payees


def save(out: Path, events, sessions, users, payees):
    out.mkdir(parents=True, exist_ok=True)
    events.to_parquet(out / "events.parquet", index=False)
    sessions.to_parquet(out / "sessions.parquet", index=False)
    users.to_parquet(out / "users.parquet", index=False)
    payees.to_parquet(out / "payees.parquet", index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-sessions", type=int, default=10_000)
    ap.add_argument("--scam-rate", type=float, default=0.2,
                    help="Share of scam sessions. Real prevalence is far lower; oversampled for training.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--demo", choices=SCAM_TYPOLOGIES + BENIGN_TYPOLOGIES,
                    help="Emit a single deterministic demo session of this typology instead.")
    ap.add_argument("--out", type=Path, default=Path("data/sim"))
    args = ap.parse_args()

    if args.demo:
        frames = generate_demo(args.demo)
    else:
        frames = generate(args.n_sessions, args.scam_rate, args.seed)
    save(args.out, *frames)

    events, sessions = frames[0], frames[1]
    print(f"wrote {len(sessions):,} sessions / {len(events):,} events -> {args.out}")
    print(sessions.groupby("typology").agg(n=("session_id", "size"), avg_events=("n_events", "mean"),
                                           avg_loss=("loss_amount", "mean")).round(1).to_string())


if __name__ == "__main__":
    main()
