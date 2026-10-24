"""Record one held-out test day of simulated traffic through the trained service, for the console's overview.

    python -m backend.record_auth_traffic        # -> frontend/public/data/auth_traffic.json (a few minutes)

Same simulator, seed and split as ml/auth/evaluate.py (the model was trained on days 0-35 and never saw days 45-60).
Live state is built from every day before the recorded one, then that day goes through the AuthEngine with
explanations, request by request, in time order; a challenged request is resolved with the policy's assumed
efficacies, as in the evaluation. The day is the test day with the widest mix of attacks.

Touch and typing deviations are drawn from the measured distributions (ml/auth/artifacts/*_quantiles.json), because
the HMOG and CMU datasets do not ship with the repo. Latency is in-process (features + model + SHAP + policy), no HTTP.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from ml.auth.engine import AuthEngine
from ml.auth.evaluate import VALID_END, warm_up
from ml.auth.features import build
from ml.auth.geo import ALL_PLACES
from ml.auth.model import AuthModel
from ml.auth.policy import EFFICACY, GENUINE_PASS, AuthPolicy
from ml.auth.sim import ATTACKS, DAY, T0, SimConfig, attach_bio, attach_typing, generate

OUT = Path("frontend/public/data/auth_traffic.json")
LAST_DAY = 60


def pick_day(events: list[dict]) -> int:
    """The test day with the most attack types, then the most attack requests."""
    best, key = VALID_END, (-1, -1)
    for d in range(VALID_END, LAST_DAY):
        lo, hi = T0 + d * DAY, T0 + (d + 1) * DAY
        kinds = Counter(r["label"]["scenario"] for r in events if lo <= r["ts"] < hi and r["label"]["is_attack"])
        k = (len(kinds), sum(kinds.values()))
        if k > key:
            best, key = d, k
    return best


def main(seed: int = 7):
    t0 = time.time()
    events = generate(SimConfig(seed=seed))
    attach_bio(events, None, None, seed)
    attach_typing(events, None, seed)
    day = pick_day(events)
    print(f"{len(events):,} requests generated; recording test day {day} ({time.time() - t0:.0f}s)")

    state, _ = warm_up(events, day)
    eng = AuthEngine(AuthModel.load(), AuthPolicy(), state)
    rng = np.random.default_rng(seed)
    lo, hi = T0 + day * DAY, T0 + (day + 1) * DAY
    rows = []
    for r in events:
        if r["ts"] < lo:
            continue
        if r["ts"] >= hi:
            break
        lab = r["label"]
        q = {k: (dict(v) if isinstance(v, dict) else v) for k, v in r.items()
             if k not in ("label", "bio_subject", "bio_profile", "typing_owner", "typing_profile")}
        # the step-up the policy would pick if it challenged, and whether the SIM just changed (no call-back then):
        # lets the console's policy tuner re-decide every request with other costs (features are read-only)
        f0, ctx0 = build(q, eng.state)
        cand, sim_fresh = eng.policy.choose_challenge(f0, ctx0), bool(f0.get("sim_fresh", 0) > 0)
        d = eng.authenticate(q)
        final, ctype = d["decision"], d["challenge_type"]
        passed = None
        if final == "challenge":
            u = rng.random()
            passed = bool(u >= EFFICACY[ctype][lab["scenario"]] if lab["is_attack"] else u < GENUINE_PASS[ctype])
            final = eng.verify_challenge(d["decision_id"], passed)["decision"]
        top = [[s["name"], round(s["contribution"], 2)] for s in d["signals"][:3] if s["contribution"] >= 0.1]
        fam = d["family_contribution"]
        rows.append({
            "t": round(r["ts"] - lo, 1), "u": r["user_id"], "ch": r["channel"], "ev": r["event_type"],
            "pf": r["device"]["platform"], "city": r["network"].get("city"), "amt": round(float(r["transaction"]["amount"]), 2),
            "d": d["decision"], "c": ctype, "f": final, "pass": passed, "p": float(f"{d['risk_score']:.4g}"),
            "ms": round(d["latency_ms"], 2), "atk": lab["scenario"] if lab["is_attack"] else None,
            "kind": lab["scenario"], "diff": None if lab["difficulty"] is None else round(float(lab["difficulty"]), 2),
            "fam": [round(fam["behaviour"], 2), round(fam["device"], 2), round(fam["transaction"], 2)],
            "top": top, "rule": d["rule"], "cc": cand, "sf": sim_fresh,
        })
    atk = [x for x in rows if x["atk"]]
    meta = {
        "about": "One held-out test day of the account-takeover simulator, replayed through the trained service "
                 "(backend/record_auth_traffic.py). Attacks and genuine behaviour are simulated; touch and typing "
                 "deviations are drawn from the measured distributions; challenge outcomes use the policy's assumed "
                 "efficacies; latency is in-process.",
        "day": day, "date": time.strftime("%Y-%m-%d", time.gmtime(lo + 5.5 * 3600)), "seed": seed,
        "model_version": eng.model.meta.get("version"), "requests": len(rows), "attacks": len(atk),
        "attack_types": sorted({x["atk"] for x in atk}), "all_attack_types": list(ATTACKS),
        "places": {k: [round(v[0], 3), round(v[1], 3)] for k, v in ALL_PLACES.items()},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"meta": meta, "rows": rows}, separators=(",", ":")), encoding="utf-8")
    by = Counter(x["d"] for x in rows)
    stopped = sum(x["f"] == "block" for x in atk)
    print(f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB): {len(rows):,} requests, {dict(by)}, "
          f"attacks stopped {stopped}/{len(atk)} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
