"""Train the authentication model and evaluate the full decision service on the account-takeover simulator.

    python -m ml.auth.evaluate                 # ~3 min with the HMOG cache (CUDA optional) -> ml/reports/auth.{md,json}
                                               #   + ml/auth/artifacts/auth_xgb.{json,meta.json}

Protocol
  1. Generate 60 days of traffic (ml/auth/sim.py); touch windows scored by the real HMOG BiLSTM + LDA model.
  2. Days 0-45: replay requests in time order through the live-state feature builder; history is committed for genuine
     requests only (attacks in this period are assumed caught / charged back later). Train on days 0-35, early-stop
     and set the prior on days 35-45.
  3. Days 45-60 (test): replay through the *service* (AuthEngine: model -> policy -> state) starting from the day-45 state.
     A challenged request is resolved by simulation: a genuine user passes with GENUINE_PASS[c], an attacker is stopped
     with EFFICACY[c][attack] (policy.py; assumptions). Completed requests change the state, exactly as in serving.
  4. The same replay for: models trained on one signal family only, "SMS OTP on every payment", and a rules engine.
Everything is simulated: the numbers validate the pipeline and compare designs; they are not real-world accuracy.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .engine import AuthEngine
from .features import FAMILY, FEATURES, build
from .model import ART, AuthModel
from .policy import EFFICACY, GENUINE_PASS, AuthPolicy
from .sim import ATTACKS, DAY, T0, SimConfig, attach_bio, generate, save_bio_quantiles
from .state import AuthState, MemoryKV

REPORTS = Path("ml/reports")
TRAIN_END, VALID_END = 35, 45


# ---------------------------------------------------------------------------- baselines (same interface as AuthPolicy)
class OtpEverything(AuthPolicy):
    """Today's default: an SMS OTP on every payment, nothing else."""
    def decide(self, p, amount, f, ctx):
        return {"decision": "challenge", "challenge_type": "sms_otp", "rule": "otp_always", "expected_cost": {}}


class RulesEngine(AuthPolicy):
    """A typical static rule set: OTP for new devices, new cities or large amounts; block emulators on hosting IPs."""
    def decide(self, p, amount, f, ctx):
        if f["emulator"] and (f["ip_datacenter"] or f["ip_anonymiser"]):
            return {"decision": "block", "challenge_type": None, "rule": "emulator_hosting_ip", "expected_cost": {}}
        if ctx.get("last_fail_age_s") is not None and ctx["last_fail_age_s"] <= 1800:
            return {"decision": "block", "challenge_type": None, "rule": "recent_fail", "expected_cost": {}}
        if f["device_new"] or f["new_city"] or (f["amt_z"] == f["amt_z"] and f["amt_z"] > 2.0) or amount > 25000:
            return {"decision": "challenge", "challenge_type": "sms_otp", "rule": "rules", "expected_cost": {}}
        return {"decision": "allow", "challenge_type": None, "rule": None, "expected_cost": {}}


# ---------------------------------------------------------------------------- phases
def warm_up(events: list[dict], until_day: float) -> tuple[AuthState, pd.DataFrame]:
    """Phase 1: causal features for days [0, until_day) with oracle commits; returns the state and the feature table."""
    state = AuthState(MemoryKV())
    rows = []
    end = T0 + until_day * DAY
    for r in events:
        if r["ts"] >= end:
            break
        f, _ = build(r, state)
        lab = r["label"]
        rows.append({**f, "y": int(lab["is_attack"]), "scenario": lab["scenario"], "day": (r["ts"] - T0) / DAY,
                     "event_id": r["event_id"]})
        state.record_attempt(r["user_id"], r["device"]["device_id"], r["network"]["ip"], r["ts"])
        if not lab["is_attack"]:
            state.commit(r["user_id"], r, r["ts"])
    return state, pd.DataFrame(rows)


def replay(events: list[dict], state: AuthState, model: AuthModel, policy: AuthPolicy, from_day: float, seed: int = 0) -> pd.DataFrame:
    """Phase 3: the test period through the service, with simulated challenge outcomes."""
    rng = np.random.default_rng(seed)
    eng = AuthEngine(model, policy, state)
    start = T0 + from_day * DAY
    out = []
    for r in events:
        if r["ts"] < start:
            continue
        lab = r["label"]
        q = {k: (dict(v) if isinstance(v, dict) else v) for k, v in r.items() if k not in ("label", "bio_subject", "bio_profile")}
        d = eng.authenticate(q, explain=False)
        final, ctype = d["decision"], d["challenge_type"]
        if final == "challenge":
            u = rng.random()
            passed = u >= EFFICACY[ctype][lab["scenario"]] if lab["is_attack"] else u < GENUINE_PASS[ctype]
            final = eng.verify_challenge(d["decision_id"], passed)["decision"]
        out.append({"event_id": r["event_id"], "y": int(lab["is_attack"]), "scenario": lab["scenario"],
                    "attack_id": lab["attack_id"], "difficulty": lab["difficulty"], "event_type": r["event_type"],
                    "amount": r["transaction"]["amount"], "p": d["risk_score"], "first": d["decision"],
                    "challenge": ctype, "final": final})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------- metrics
def summarise(t: pd.DataFrame) -> dict:
    g, a = t[t.y == 0], t[t.y == 1]
    res = {"genuine_requests": len(g),
           "genuine_challenged_pct": round(100 * (g["first"] == "challenge").mean(), 2),
           "genuine_blocked_pct": round(100 * (g["final"] == "block").mean(), 3),
           "genuine_first_blocked_pct": round(100 * (g["first"] == "block").mean(), 3),
           "attack_requests": len(a),
           "attacks_stopped_pct": round(100 * (a["final"] == "block").mean(), 2),
           "attack_money_stopped_pct": round(100 * a.loc[a["final"] == "block", "amount"].sum() / max(a["amount"].sum(), 1), 2),
           "attack_campaigns": int(a["attack_id"].nunique()),
           "campaigns_with_any_success_pct": round(100 * a.groupby("attack_id")["final"].apply(lambda s: (s == "allow").any()).mean(), 2),
           "challenge_mix": {k: int(v) for k, v in t.loc[t["first"] == "challenge", "challenge"].value_counts().items()},
           "per_scenario": {}}
    for s in ["genuine", "routine", "new_phone", "travel", "big_purchase", "web", *ATTACKS]:
        x = t[t.scenario == s] if s != "genuine" else g
        if len(x):
            res["per_scenario"][s] = {"n": len(x), "allow_first": round(100 * (x["first"] == "allow").mean(), 1),
                                      "challenge_first": round(100 * (x["first"] == "challenge").mean(), 1),
                                      "block_first": round(100 * (x["first"] == "block").mean(), 1),
                                      "final_blocked": round(100 * (x["final"] == "block").mean(), 1)}
    return res


def latency(events: list[dict], state: AuthState, model: AuthModel, from_day: float, n: int = 2000) -> dict:
    eng = AuthEngine(model, AuthPolicy(), AuthState(state.kv.snapshot()))
    start = T0 + from_day * DAY
    sample = [r for r in events if r["ts"] >= start][:n]
    ms = []
    for r in sample:
        q = {k: (dict(v) if isinstance(v, dict) else v) for k, v in r.items() if k not in ("label", "bio_subject", "bio_profile")}
        t0 = time.perf_counter()
        eng.authenticate(q, explain=True)
        ms.append(1000 * (time.perf_counter() - t0))
    ms = np.array(ms)
    return {"n": len(ms), "p50_ms": round(float(np.percentile(ms, 50)), 2), "p95_ms": round(float(np.percentile(ms, 95)), 2),
            "p99_ms": round(float(np.percentile(ms, 99)), 2), "note": "in-process: features + model + SHAP + policy + state, CPU, memory state; excludes touch scoring and HTTP"}


# ---------------------------------------------------------------------------- report
def write_report(R: dict, path: Path = REPORTS / "auth.md"):
    L = ["# Transaction authentication (BIOS) — allow / challenge / block on the account-takeover simulator", "",
         "> Simulated customers and attacks (ml/auth/sim.py); touch windows are real HMOG gestures scored by the real "
         "BiLSTM + LDA model; challenge efficacies and genuine pass rates are **assumptions** (ml/auth/policy.py). "
         "The numbers validate the service and compare designs; they are not real-world accuracy.", "",
         f"Traffic: {R['data']['users']:,} customers, {R['data']['requests']:,} requests over 60 days "
         f"({R['data']['attack_requests']:,} attack requests); touch scores: {R['data']['bio']}. "
         f"Train days 0-{TRAIN_END}, valid {TRAIN_END}-{VALID_END}, test {VALID_END}-60 replayed through the service. "
         f"Assumed real-world attack prevalence: {R['model']['real_prior']:.1%} of requests "
         f"(simulator: {R['model']['fit_prior']:.2%}).", "",
         "## Ranking quality (test requests, full model)", "",
         "| model | ROC-AUC | PR-AUC |", "|---|---|---|"]
    for k, v in R["ranking"].items():
        L.append(f"| {k} | {v['roc_auc']:.4f} | {v['pr_auc']:.4f} |")
    L += ["", "Family-only models are trained on the same rows with only that family's features (ablation).", "",
          "## Decisions on the test period (replayed through the service)", "",
          "| design | genuine challenged | genuine blocked (final) | attack requests stopped | attack money stopped | attack campaigns with any success |",
          "|---|---|---|---|---|---|"]
    for k, v in R["designs"].items():
        L.append(f"| {k} | {v['genuine_challenged_pct']}% | {v['genuine_blocked_pct']}% | {v['attacks_stopped_pct']}% | "
                 f"{v['attack_money_stopped_pct']}% | {v['campaigns_with_any_success_pct']}% |")
    full = R["designs"]["risk engine (all signals)"]
    L += ["", "## Per scenario, risk engine (first decision; final = after the challenge)", "",
          "| scenario | requests | allow | challenge | block | finally blocked |", "|---|---|---|---|---|---|"]
    for s, v in full["per_scenario"].items():
        L.append(f"| {s} | {v['n']} | {v['allow_first']}% | {v['challenge_first']}% | {v['block_first']}% | {v['final_blocked']}% |")
    L += ["", f"Challenge mix (risk engine): {full['challenge_mix']}", "",
          "## Attacks by difficulty (risk engine)", "", "| difficulty | attack requests | stopped |", "|---|---|---|"]
    for k, v in R["difficulty"].items():
        L.append(f"| {k} | {v['n']} | {v['stopped']}% |")
    L += ["", "## Latency", "", f"{R['latency']['note']}: p50 {R['latency']['p50_ms']} ms, p95 {R['latency']['p95_ms']} ms, "
          f"p99 {R['latency']['p99_ms']} ms over {R['latency']['n']} requests.", "",
          "## Most important features (gain)", "", "| feature | family | gain |", "|---|---|---|"]
    for f, g in R["importance"][:15]:
        L.append(f"| {f} | {FAMILY[f]} | {g:.1f} |")
    L += ["", "## Assumptions", "", "P(challenge stops the attack):", "", "| challenge | " + " | ".join(ATTACKS) + " | genuine pass |",
          "|---|" + "---|" * (len(ATTACKS) + 1)]
    for c, row in EFFICACY.items():
        L.append(f"| {c} | " + " | ".join(f"{row[a]:.2f}" for a in ATTACKS) + f" | {GENUINE_PASS[c]:.2f} |")
    L += ["", "Policy costs (rupee-equivalents): " + json.dumps({"friction": AuthPolicy().friction, "block_cost": AuthPolicy().block_cost,
          "login_exposure": AuthPolicy().login_exposure, "block_min_p": AuthPolicy().block_min_p}), ""]
    path.write_text("\n".join(L), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=SimConfig.n_users)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--real-prior", type=float, default=0.002)
    ap.add_argument("--no-hmog", action="store_true", help="use the saved touch-score quantiles instead of HMOG")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args(argv)
    t_start = time.time()

    bank = scorer = None
    if not a.no_hmog:
        from ml.sim.hmog_bank import HmogBank
        bank = HmogBank.load()
        if bank is not None:
            import torch
            from ml.models.biometrics.scorer import BioScorer
            scorer = BioScorer("cuda" if torch.cuda.is_available() else "cpu")
    events = generate(SimConfig(n_users=a.users, seed=a.seed), bank)
    how = attach_bio(events, bank, scorer, a.seed)
    if how == "hmog" and not a.no_save:
        save_bio_quantiles(events)
    print(f"{len(events):,} requests, touch={how} ({time.time() - t_start:.0f}s)")

    state, tab = warm_up(events, VALID_END)
    tr, va = tab[tab.day < TRAIN_END], tab[tab.day >= TRAIN_END]
    print(f"features: train {len(tr):,} ({tr.y.sum()} attacks), valid {len(va):,} ({va.y.sum()}) ({time.time() - t_start:.0f}s)")

    models = {"risk engine (all signals)": AuthModel(real_prior=a.real_prior).fit(tr, tr.y, va, va.y)}
    for fam in ("behaviour", "device", "transaction"):
        models[f"{fam} signals only"] = AuthModel(features=[f for f in FEATURES if FAMILY[f] == fam],
                                                  real_prior=a.real_prior).fit(tr, tr.y, va, va.y)
    full = models["risk engine (all signals)"]

    designs, tables = {}, {}
    for name, m in models.items():
        tables[name] = replay(events, AuthState(state.kv.snapshot()), m, AuthPolicy(), VALID_END)
        designs[name] = summarise(tables[name])
        print(f"{name}: {designs[name]['genuine_challenged_pct']}% genuine challenged, {designs[name]['attacks_stopped_pct']}% attacks stopped")
    for name, pol in (("SMS OTP on every payment", OtpEverything()), ("rules engine + SMS OTP", RulesEngine())):
        tables[name] = replay(events, AuthState(state.kv.snapshot()), full, pol, VALID_END)
        designs[name] = summarise(tables[name])
        print(f"{name}: {designs[name]['genuine_challenged_pct']}% genuine challenged, {designs[name]['attacks_stopped_pct']}% attacks stopped")

    ranking = {}
    for name, m in models.items():
        t = tables[name]
        ranking[name] = {"roc_auc": float(roc_auc_score(t.y, t.p)), "pr_auc": float(average_precision_score(t.y, t.p))}
    tf = tables["risk engine (all signals)"]
    att = tf[tf.y == 1].copy()
    att["band"] = pd.cut(att["difficulty"], [0, 0.33, 0.66, 1.0], include_lowest=True, labels=["easy (0-0.33)", "medium", "hard (0.66-1)"])
    difficulty = {str(k): {"n": int(len(x)), "stopped": round(100 * (x["final"] == "block").mean(), 1)}
                  for k, x in att.groupby("band", observed=True)}
    gain = full.booster.get_score(importance_type="gain")
    importance = sorted(((f, gain.get(f, 0.0)) for f in FEATURES), key=lambda kv: -kv[1])
    R = {"data": {"users": a.users, "requests": len(events), "attack_requests": int(sum(r["label"]["is_attack"] for r in events)),
                  "bio": how, "seed": a.seed},
         "model": {"real_prior": a.real_prior, "fit_prior": full.fit_prior, "best_iteration": full.best_iteration},
         "ranking": ranking, "designs": designs, "difficulty": difficulty, "importance": importance,
         "latency": latency(events, state, full, VALID_END), "seconds": round(time.time() - t_start)}
    print(json.dumps({k: R[k] for k in ("ranking", "latency")}, indent=1))
    if not a.no_save:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "auth.json").write_text(json.dumps(R, indent=2, default=str))
        write_report(R)
        full.save(ART, "auth_xgb", extra={"version": f"auth-sim-s{a.seed}", "trained_on": "ml.auth.sim (synthetic) + HMOG touch",
                                          "test_roc_auc": round(ranking["risk engine (all signals)"]["roc_auc"], 4)})
    print(f"done in {time.time() - t_start:.0f}s")
    return R


if __name__ == "__main__":
    main()
