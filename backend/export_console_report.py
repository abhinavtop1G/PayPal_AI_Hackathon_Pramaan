"""Collect the evaluation reports the console's Model page and typing lab show into one small file.

    python -m backend.export_console_report        # -> frontend/public/data/model_report.json

Reads only what the evaluation scripts already wrote (ml/reports/*.json, backend/reports/auth_latency.md) and the
demo customer's typing pack, so every number on the page traces back to a report in the repo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from ml.auth.policy import EFFICACY, GENUINE_PASS, AuthPolicy
from ml.models.keystroke.protocol import profile_manhattan

OUT = Path("frontend/public/data/model_report.json")
R = Path("ml/reports")


def _load(name: str) -> dict:
    return json.loads((R / name).read_text(encoding="utf-8"))


def http_latency(path: Path = Path("backend/reports/auth_latency.md")) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(POST [^|]+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
        if m:
            rows.append({"what": m[1], "n": int(m[2]), "p50": float(m[3]), "p95": float(m[4]), "p99": float(m[5])})
    return rows


def sessions_mean(ks: dict) -> dict:
    """Protocol A of ml/reports/keystroke_cmu.md (enrol sessions 1-4, test 5-8, unseen users): per-user EER per
    method, mean and std over the training seeds, for one try and three tries."""
    seeds = list(ks["per_seed"])
    out: dict = {}
    for m in ks["per_seed"][seeds[0]]["sessions"]:
        for k in ("one_try", "three_tries"):
            v = [ks["per_seed"][s]["sessions"][m][k]["per_user_eer_mean"] for s in seeds]
            out.setdefault(m, {})[k] = [round(float(np.mean(v)), 4), round(float(np.std(v)), 4)]
    return out


def typing_demo(path: Path = Path("ml/auth/artifacts/demo_keystrokes.json")) -> dict:
    """The demo customer's scaled-Manhattan profile, and how far her own later attempts and others' attempts land
    from it (the console's typing lab plots a new attempt against these)."""
    k = json.loads(path.read_text())
    enrol = np.asarray(k["enrolment"], dtype=float)
    mu, mad = profile_manhattan(enrol)

    def dist(x):
        return float((np.abs(np.asarray(x, dtype=float) - mu) / mad).sum())

    return {"password": k["password"], "profile": {"mean": [round(float(v), 5) for v in mu],
                                                   "mad": [round(float(v), 5) for v in mad], "n": len(enrol)},
            "distances": {p: [round(dist(a), 2) for a in k["attempts"][p]] for p in ("normal", "coerced", "remote", "bot")}}


def policy() -> dict:
    """The decision policy's parameters (ml/auth/policy.py), for the console's policy tuner: what the policy assumes a
    step-up achieves and costs, and what the evaluation simulates it achieving per attack type."""
    p = AuthPolicy()
    return {"assumed_efficacy": p.efficacy, "friction": p.friction, "block_cost": p.block_cost,
            "login_exposure": p.login_exposure, "block_min_p": p.block_min_p,
            "simulated_efficacy": EFFICACY, "genuine_pass": GENUINE_PASS}


def main():
    auth = _load("auth.json")
    ks = _load("keystroke_cmu.json")
    bio = _load("biometrics_hmog.json")
    seed = str(ks["selected_seed"])
    keep = ("genuine_challenged_pct", "genuine_blocked_pct", "attacks_stopped_pct", "attack_money_stopped_pct",
            "campaigns_with_any_success_pct", "challenge_mix", "attack_requests", "genuine_requests")
    report = {
        "auth": {
            "data": auth["data"], "model": auth["model"], "ranking": auth["ranking"], "difficulty": auth["difficulty"],
            "importance": [[f, round(g, 2)] for f, g in auth["importance"]], "latency": auth["latency"],
            "designs": {name: {**{k: d[k] for k in keep if k in d},
                               "per_scenario": {s: v["final_blocked"] for s, v in d["per_scenario"].items()},
                               "first": {s: [v["allow_first"], v["challenge_first"], v["block_first"]]
                                         for s, v in d["per_scenario"].items()}}
                        for name, d in auth["designs"].items()},
        },
        "http_latency": http_latency(),
        "keystroke": {"published": ks["published_km"], "all_users": ks["km_all_users"], "users": ks["users"],
                      "heldout": ks["per_seed"][seed]["km_heldout"], "sessions": sessions_mean(ks),
                      "selected_seed": int(seed)},
        "touch": {split: {n: {m: v["eer"][0] for m, v in bio[split][n].items() if isinstance(v, dict)} for n in ("n10", "n20")}
                  for split in ("valid", "test")},
        "typing_demo": typing_demo(),
        "policy": policy(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
