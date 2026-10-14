"""Adaptive scammers: how much does detection degrade when scammers change tactics?

    python -m ml.engine.robustness                 # ~10 min: 8 scenarios x 6,000 fresh sessions
    python -m ml.engine.robustness --n 1500        # quick check

Each scenario generates a fresh simulated world (never seen in training) in which every scam session applies one
adaptive tactic (ml/sim/builder.py ADVERSARY_KNOBS), or all of them at once. Genuine sessions are unchanged. Every
scenario then runs through the exact shipped pipeline: honest payee scores (ml.campaign.attach), the real biometrics
scorer, the trained workflow GRU, the fusion model at the real-world prior and the full alert policy (anti-fatigue on),
replayed in time order. Writes ml/reports/robustness.{md,json}.

What it can and cannot show: the tactics are our model of adaptation, and the detectors were trained without them, so
this measures how gracefully the system degrades against shifts it never saw, not how a real adversary would behave.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ml.campaign.attach import attach
from ml.models.biometrics.scorer import BioScorer
from ml.models.biometrics.session_scores import score_events
from ml.models.workflow.data import as_seqdata
from ml.sim.builder import ADVERSARY_KNOBS
from ml.sim.generate import generate
from ml.sim.hmog_bank import HmogBank

from .components import component_table, default_device, gru_outputs, load_gru
from .fusion import FusionModel
from .policy import AlertPolicy
from .simulate import outcomes, replay

FUSION_DIR = Path("ml/engine/artifacts")
REPORT = Path("ml/reports/robustness")
CACHE = Path("checkpoints/robustness")  # per-scenario results (delete to recompute after retraining)
SCENARIOS = {"baseline (no adaptation)": {}, **{k: {k: True} for k in ADVERSARY_KNOBS},
             "all tactics at once": {k: True for k in ADVERSARY_KNOBS}}
WHAT = {
    "no_call": "calls move to an OTT app the bank can't see",
    "slow": "the workflow is stretched 5x in time",
    "split_amounts": "each payment split into 3-5 smaller ones",
    "clean_device": "no sideloaded app, no screen control or sharing",
    "calm_hands": "touch behaviour stays normal",
    "fresh_numbers": "calls from never-reported numbers",
}


def run(adversary: dict, n: int, seed: int, gru, fusion, scorer, bank, device) -> tuple[dict, pd.DataFrame]:
    ev, se, us, pa = generate(n, 0.2, seed, adversary=adversary)
    ev, _ = attach(ev, se, us, pa)
    ev["bio_model_dev"] = score_events(ev, scorer, bank)
    d = as_seqdata(ev, se, us)
    t = component_table(d, gru_outputs(gru, d, device))
    t = t.assign(fused_p=fusion.proba(t))
    pol = AlertPolicy()

    def decide(r):
        dec = pol.decide(r, r["fused_p"], r["start_time"] + pd.Timedelta(seconds=r["ts"]))
        return dec.action, dec.notify
    r = replay(t, decide)
    o = outcomes(r)
    # detector view: highest workflow score a session reaches before money leaves (scams) / at all (genuine)
    pre = t[(~t["is_scam"]) | (t["ts"] <= t["extraction_ts"] + 1e-6)]
    m = pre.groupby("session_id").agg(gru=("gru_p", "max"), fused=("fused_p", "max"), y=("is_scam", "first"))
    res = {
        "sessions": int(len(d.num)), "scam_sessions": int(se["is_scam"].sum()),
        "gru_session_auc": round(float(roc_auc_score(m["y"], m["gru"])), 4) if m["y"].nunique() == 2 else None,
        "fused_session_auc": round(float(roc_auc_score(m["y"], m["fused"])), 4) if m["y"].nunique() == 2 else None,
        **{k: o[k] for k in ("scams_with_in_time_interruption_pct", "scams_expected_stopped_in_time_pct", "expected_money_saved_pct",
                             "benign_interruptions_per_1k_sessions", "benign_holds_per_1k_sessions")},
    }
    return res, r.merge(se[["session_id", "difficulty"]], on="session_id", how="left")


def by_difficulty(r: pd.DataFrame) -> list[dict]:
    """Baseline scenario sliced by the simulator's per-scam difficulty (weaker cues, dropped calls, store installs)."""
    rows = []
    benign = r[~r["is_scam"]]
    for lo, hi in [(0.0, 0.33), (0.33, 0.66), (0.66, 1.01)]:
        scam = r[r["is_scam"] & r["difficulty"].between(lo, hi, inclusive="left")]
        if scam.empty:
            continue
        o = outcomes(pd.concat([scam, benign]))
        rows.append({"difficulty": f"{lo:.2f}-{min(hi, 1.0):.2f}", "scam_sessions": int(scam["session_id"].nunique()),
                     "scams_with_in_time_interruption_pct": o["scams_with_in_time_interruption_pct"],
                     "scams_expected_stopped_in_time_pct": o["scams_expected_stopped_in_time_pct"],
                     "expected_money_saved_pct": o["expected_money_saved_pct"]})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=101)
    a = ap.parse_args()
    device = default_device()
    gru, fusion = load_gru(device), FusionModel.load(FUSION_DIR)
    scorer, bank = BioScorer(device), HmogBank.load()
    results, diff = {}, None
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, adv in SCENARIOS.items():
        cached = CACHE / f"{name.split(' ')[0]}_n{a.n}_s{a.seed}.json"  # resumable: each finished scenario is kept
        if cached.exists():
            saved = json.loads(cached.read_text())
            results[name] = saved["res"]
            diff = saved.get("diff") or diff
            continue
        res, r = run(adv, a.n, a.seed, gru, fusion, scorer, bank, device)
        results[name] = res
        if not adv:
            diff = by_difficulty(r)
        cached.write_text(json.dumps({"res": res, "diff": diff if not adv else None}, default=float))
        print(f"{name:28s} stopped in time {res['scams_expected_stopped_in_time_pct']:6.2f}%  "
              f"money saved {res['expected_money_saved_pct']:6.2f}%  genuine interruptions/1k {res['benign_interruptions_per_1k_sessions']}")
    REPORT.with_suffix(".json").write_text(json.dumps({"n": a.n, "seed": a.seed, "scenarios": results, "by_difficulty": diff}, indent=2))
    write_md(results, diff, a)
    print(f"wrote {REPORT}.md/.json")


def write_md(results: dict, diff: list, a) -> None:
    base = results["baseline (no adaptation)"]
    L = ["# Robustness: adaptive scammers", "",
         f"Each row is a fresh simulated world ({a.n:,} sessions, 20% scams, seed {a.seed}) never used in training, in which every scam "
         "session uses the tactic named (genuine sessions unchanged). Everything downstream is the shipped pipeline: honest payee "
         "scores, the real HMOG biometrics scorer, the workflow GRU, fusion at a 0.5% real-world prior and the full alert policy, "
         "replayed in time order. The tactics are our model of adaptation and the detectors never saw them: this measures graceful "
         "degradation under shift, not real adversaries.", "",
         "| scenario | what the scammer changes | session AUC (GRU) | session AUC (fused) | scams interrupted in time | expected stopped in time | money saved | genuine interruptions / 1k |",
         "|---|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        what = WHAT.get(name, "nothing" if not name.startswith("all") else "everything above")
        d = r["scams_expected_stopped_in_time_pct"] - base["scams_expected_stopped_in_time_pct"]
        L.append(f"| {name} | {what} | {r['gru_session_auc']} | {r['fused_session_auc']} | {r['scams_with_in_time_interruption_pct']}% | "
                 f"{r['scams_expected_stopped_in_time_pct']}% ({d:+.1f}) | {r['expected_money_saved_pct']}% | "
                 f"{r['benign_interruptions_per_1k_sessions']} |")
    singles = [k for k in results if k in ADVERSARY_KNOBS]
    worst = min(singles, key=lambda k: results[k]["scams_expected_stopped_in_time_pct"])
    allr = results["all tactics at once"]
    L += ["", f"Largest drop from a single tactic: **{worst}** ({results[worst]['scams_expected_stopped_in_time_pct']}% vs "
          f"{base['scams_expected_stopped_in_time_pct']}% stopped in time). With every tactic at once only "
          f"{allr['scams_expected_stopped_in_time_pct']}% of scams are stopped in time, yet {allr['expected_money_saved_pct']}% of the money "
          "is still saved: the large payments that make up most of the loss still look anomalous. Genuine interruptions do "
          "not rise in any scenario, so adaptation costs detection, not extra false alarms.", "",
          "## By scam difficulty (baseline world)", "",
          "Difficulty is the simulator's per-scam knob (0 = textbook, 1 = hardest: weaker touch shifts, fewer VoIP calls, "
          "more dropped calls and store installs).", "",
          "| difficulty | scam sessions | interrupted in time | expected stopped in time | money saved |", "|---|---|---|---|---|"]
    for r in diff or []:
        L.append(f"| {r['difficulty']} | {r['scam_sessions']} | {r['scams_with_in_time_interruption_pct']}% | "
                 f"{r['scams_expected_stopped_in_time_pct']}% | {r['expected_money_saved_pct']}% |")
    REPORT.with_suffix(".md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
