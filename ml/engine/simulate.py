"""Replay test sessions through fusion + alert policy and measure stopping power vs alert fatigue.

    python -m ml.engine.simulate

Valid period is split by start time: first half (plus out-of-fold training-period GRU scores from
engine/oof.py) fits the fusion model, second half sets thresholds
for the single-threshold baselines. Test sessions are replayed in global time order so per-user
budgets carry across sessions. Scam outcomes are expected values using each tier's assumed efficacy.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ml.models.workflow.data import SeqData
from ml.models.workflow.metrics import LOOKALIKES, evaluate

from .components import build_tables, subset
from .fusion import FusionModel
from .oof import OUT as OOF
from .policy import BY_NAME, AlertPolicy

REPORT_DIR = Path("ml/reports")
BUDGET = 0.01
PRIOR_SWEEP = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05)


def per_event(t: pd.DataFrame, d: SeqData, score: np.ndarray, sessions: np.ndarray) -> list[np.ndarray]:
    """Scatter payment-attempt scores back to per-session event arrays (other events score 0)."""
    out = [np.zeros(len(d.num[i])) for i in sessions]
    pos = {s: k for k, s in enumerate(sessions)}
    for si, ei, sc in zip(t["session_idx"], t["event_idx"], score):
        out[pos[si]][ei] = sc
    return out


def session_threshold(t: pd.DataFrame, score: np.ndarray, budget: float) -> float:
    m = pd.Series(score, index=t.index).groupby(t["session_id"]).max()
    benign = t.groupby("session_id")["is_scam"].first()
    return float(np.quantile(m[~benign.loc[m.index]], 1 - budget, method="higher")) + 1e-12


def replay(t: pd.DataFrame, decide) -> pd.DataFrame:
    """decide(row) -> (action, notify). Rows are processed in global time order."""
    order = (t["start_time"] + pd.to_timedelta(t["ts"], unit="s")).sort_values(kind="stable").index
    acts, notes = pd.Series("allow", index=t.index), pd.Series(False, index=t.index)
    for i in order:
        acts[i], notes[i] = decide(t.loc[i])
    return t.assign(action=acts, notify=notes)


def threshold_policy(score_col: str, thr: float):
    """Single-threshold baseline: hold at the first risky attempt; the session then stays on hold."""
    held = set()

    def decide(r):
        if r["session_id"] in held:
            return "hold", False
        if r[score_col] >= thr:
            held.add(r["session_id"])
            return "hold", True
        return "allow", False
    return decide


def outcomes(r: pd.DataFrame) -> dict:
    """Expected outcomes. Only new interruptions (notify=True) carry their tier's efficacy: a payment that stays held
    in an already-held session is the same hold, not another independent 90% chance of stopping the scam."""
    tier_eff = r["action"].map(lambda a: BY_NAME[a].efficacy if a in BY_NAME else 0.0)
    r = r.assign(eff=tier_eff.where(r["notify"].astype(bool), 0.0), interrupt=r["notify"].astype(bool))
    r = r.sort_values(["session_id", "ts"])
    # P(scam already stopped) after each attempt's action, cumulative within the session
    r["p_stop"] = 1 - (1 - r["eff"]).groupby(r["session_id"]).cumprod()
    scam, benign = r[r["is_scam"]], r[~r["is_scam"]]
    in_time = scam[scam["ts"] <= scam["extraction_ts"] + 1e-6]
    stop_in_time = in_time.groupby("session_id")["p_stop"].max().reindex(scam["session_id"].unique(), fill_value=0)
    # a scam payment is prevented if any action at or before it stopped the flow
    pay = scam[scam["in_progress"] == 1]
    saved = (pay["amount"] * pay["p_stop"]).sum() / pay["amount"].sum()
    benign = benign.assign(new_hold=(benign["action"] == "hold") & benign["interrupt"])
    b_sess = benign.groupby("session_id").agg(n=("interrupt", "sum"), hold=("new_hold", "sum"),
                                              user=("user_id", "first"), typ=("typology", "first"))
    b_user = b_sess.groupby("user")["n"].sum()
    return {
        "benign_interruptions_per_1k_sessions": round(1000 * b_sess["n"].sum() / len(b_sess), 1),
        "benign_sessions_interrupted_pct": round(100 * (b_sess["n"] > 0).mean(), 2),
        "benign_holds_per_1k_sessions": round(1000 * b_sess["hold"].sum() / len(b_sess), 1),
        "benign_users_interrupted_pct": round(100 * (b_user > 0).mean(), 2),
        "benign_users_interrupted_3plus_pct": round(100 * (b_user >= 3).mean(), 2),
        "lookalike_interrupted_pct": {t: round(100 * (b_sess.loc[b_sess["typ"] == t, "n"] > 0).mean(), 1) for t in LOOKALIKES},
        "lookalike_sessions": {t: int((b_sess["typ"] == t).sum()) for t in LOOKALIKES},
        "scams_with_in_time_interruption_pct": round(100 * (in_time.groupby("session_id")["interrupt"].any()
                                                            .reindex(stop_in_time.index, fill_value=False).mean()), 2),
        "scams_expected_stopped_in_time_pct": round(100 * stop_in_time.mean(), 2),
        "expected_money_saved_pct": round(100 * saved, 2),
        "action_mix_all_attempts": r["action"].value_counts().to_dict(),
    }


def main():
    T = build_tables()
    tv, dv = T["valid"]
    tt, dt = T["test"]
    # split valid by session start: A fits fusion, B sets thresholds
    cut = dv.sessions["start_time"].median()
    a_idx = np.flatnonzero(dv.sessions["start_time"] < cut)
    b_idx = np.flatnonzero(dv.sessions["start_time"] >= cut)
    tA, tB = tv[tv["session_idx"].isin(a_idx)], tv[tv["session_idx"].isin(b_idx)]

    oof = pd.read_parquet(OOF) if OOF.exists() else None  # python -m ml.engine.oof
    fusion = FusionModel(real_prior=0.005).fit(pd.concat([oof, tA]) if oof is not None else tA)
    fB, fT = fusion.logit(tB), fusion.logit(tt)

    # 1) detector-level comparison with the workflow protocol (thresholds on valid half B)
    dB = subset(dv, b_idx)
    all_te = np.arange(len(dt.num))
    det = {}
    for name, sB, sT in [("gru", tB["gru_p"].to_numpy(), tt["gru_p"].to_numpy()), ("fused", fB, fT)]:
        r = evaluate(per_event(tB, dv, sB, b_idx), dB, per_event(tt, dt, sT, all_te), dt)
        det[name] = {k: r[k] for k in ("payment_attempt_pr_auc", "budget_1%", "budget_5%")}

    # 2) policy comparison on test replay
    thr_gru = session_threshold(tB, tB["gru_p"].to_numpy(), BUDGET)
    thr_fused = session_threshold(tB, fB, BUDGET)
    tt = tt.assign(fused_logit=fT, fused_p=fusion.proba(tt))
    policies = {}
    policies["GRU threshold -> hold"] = replay(tt, threshold_policy("gru_p", thr_gru))
    policies["Fused threshold -> hold"] = replay(tt, threshold_policy("fused_logit", thr_fused))
    for name, pol in [("Engine (EV tiers, no anti-fatigue)", AlertPolicy(anti_fatigue=False)), ("Engine (full)", AlertPolicy())]:
        def decide(r, pol=pol):
            d = pol.decide(r, r["fused_p"], r["start_time"] + pd.Timedelta(seconds=r["ts"]))
            return d.action, d.notify
        policies[name] = replay(tt, decide)
    pol_res = {k: outcomes(v) for k, v in policies.items()}

    # operating curve: the engine's trade-off depends on the assumed real-world prior (equivalently on
    # how friction is priced), so report it across a range instead of a single point
    curve = []
    for prior in PRIOR_SWEEP:
        fusion.set_prior(prior)
        pol = AlertPolicy()
        r = replay(tt.assign(fused_p=fusion.proba(tt)), lambda row, pol=pol: (
            lambda d: (d.action, d.notify))(pol.decide(row, row["fused_p"], row["start_time"] + pd.Timedelta(seconds=row["ts"]))))
        o = outcomes(r)
        curve.append({"real_prior": prior, **{k: o[k] for k in ("benign_interruptions_per_1k_sessions", "benign_holds_per_1k_sessions",
                                                                "scams_expected_stopped_in_time_pct", "expected_money_saved_pct")},
                      "genuine_urgent_family_interrupted_pct": o["lookalike_interrupted_pct"]["genuine_urgent_family"]})
    fusion.set_prior(0.005)

    # 3) example decisions: each session replayed alone with a fresh policy (no per-user history from the replay)
    examples = []
    for typ in ["digital_arrest", "voice_clone_relative", "genuine_urgent_family", "fake_kyc_apk"]:
        engine = AlertPolicy()
        sid = tt.loc[tt["typology"] == typ, "session_id"].iloc[0]
        for _, row in tt[tt["session_id"] == sid].sort_values("ts").iterrows():
            d = engine.decide(row, row["fused_p"], row["start_time"] + pd.Timedelta(seconds=row["ts"]),
                              fusion.reasons(row.to_frame().T))
            examples.append({"typology": typ, "ts_min": round(row["ts"] / 60, 1), "amount": row["amount"],
                             "stage_pred": row["gru_stage"], "fused_p_real_prior": f"{d.p:.5f}", "action": d.action, "notify": d.notify,
                             "suppressed_by": d.suppressed_by, "reasons": d.reasons, "message_en": d.message_en,
                             "message_hi": d.message_hi})

    res = {"fusion_gain_importance": fusion.importance(), "real_prior": fusion.real_prior,
           "tiers": {t.name: {"efficacy": t.efficacy, "friction": t.friction} for t in AlertPolicy().tiers},
           "detector": det, "policies": pol_res, "operating_curve": curve, "examples": examples}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "engine.json").write_text(json.dumps(res, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    write_markdown(res, REPORT_DIR / "engine.md")
    sys.stdout.reconfigure(encoding="utf-8")
    print((REPORT_DIR / "engine.md").read_text(encoding="utf-8"))


def write_markdown(res: dict, path: Path):
    L = ["# Fusion + alert policy engine — simulator test period", "",
         "> Simulator results (near-separable data, assumed tier efficacy/friction): they validate the engine's "
         "behaviour, not real-world accuracy. Payee intelligence and behavioural deviation are simulator stand-ins "
         "for the GNN and HMOG models.", "",
         "## Fusion vs workflow GRU (1% benign false-alert budget, thresholds from valid)", "",
         "| detector | PR-AUC | scams caught in time | " + " | ".join(f"FA: {t}" for t in LOOKALIKES) + " |",
         "|---|---|---|" + "---|" * len(LOOKALIKES)]
    for k, v in res["detector"].items():
        b = v["budget_1%"]
        L.append(f"| {k} | {v['payment_attempt_pr_auc']} | {100 * b['scams_caught_in_time']:.1f}% | "
                 + " | ".join(f"{100 * b['false_alert_rate_lookalikes'][t]:.1f}%" for t in LOOKALIKES) + " |")
    sizes = res["policies"]["Engine (full)"]["lookalike_sessions"]
    L += ["", "Look-alike test sessions: " + ", ".join(f"{t} n={n}" for t, n in sizes.items())
          + " (one session moves a rate by 100/n points)."]
    g, f = res["detector"]["gru"], res["detector"]["fused"]
    worse = [t for t in LOOKALIKES if f["budget_1%"]["false_alert_rate_lookalikes"][t] > g["budget_1%"]["false_alert_rate_lookalikes"][t]]
    if f["payment_attempt_pr_auc"] < g["payment_attempt_pr_auc"] or worse:
        L += ["", f"Note: the fused score is not uniformly better than the GRU alone (PR-AUC {f['payment_attempt_pr_auc']} vs "
              f"{g['payment_attempt_pr_auc']}; more false alerts on {', '.join(worse) or 'none'}). The engine's gains below come "
              "from expected-value tiering on the fused, prior-corrected risk, not from a better ranking."]
    L += ["", f"Monotone XGBoost fusion, gain importance: {res['fusion_gain_importance']}", "",
          "## Policy comparison (test replay)", "",
          f"Tiers (efficacy / friction in ₹-equivalent, assumptions): {res['tiers']}. Real-world prior "
          f"{res['real_prior']:.1%} of payment attempts. Only a new interruption carries its tier's efficacy (a payment that "
          "stays held in an already-held session is the same hold); repeat warnings without anti-fatigue are assumed "
          "independent, which flatters the no-anti-fatigue row. Holds = new holds per 1k benign sessions.", "",
          "| policy | notifications / 1k benign sessions | holds / 1k benign | benign users interrupted | users interrupted 3+ times | "
          "scams expected stopped in time | expected money saved | " + " | ".join(f"interrupted: {t}" for t in LOOKALIKES) + " |",
          "|---|---|---|---|---|---|---|" + "---|" * len(LOOKALIKES)]
    for k, v in res["policies"].items():
        L.append(f"| {k} | {v['benign_interruptions_per_1k_sessions']} | {v['benign_holds_per_1k_sessions']} | "
                 f"{v['benign_users_interrupted_pct']}% | {v['benign_users_interrupted_3plus_pct']}% | "
                 f"{v['scams_expected_stopped_in_time_pct']}% | {v['expected_money_saved_pct']}% | "
                 + " | ".join(f"{v['lookalike_interrupted_pct'][t]}%" for t in LOOKALIKES) + " |")
    full, noaf = res["policies"]["Engine (full)"], res["policies"]["Engine (EV tiers, no anti-fatigue)"]
    keys = ["benign_interruptions_per_1k_sessions", "benign_holds_per_1k_sessions", "scams_expected_stopped_in_time_pct",
            "expected_money_saved_pct"]
    if all(full[k] == noaf[k] for k in keys):
        L += ["", "Anti-fatigue rules change nothing in this replay; the reduction in alert fatigue comes from "
              "expected-value tiering (risk x amount vs friction)."]
    else:
        L += ["", "Anti-fatigue rules: " + "; ".join(f"{k.replace('_', ' ')} {noaf[k]} -> {full[k]}" for k in keys) + "."]
    L += ["",
          "## Operating curve (full engine vs assumed real-world prior)", "",
          "| assumed prior | notifications / 1k benign | holds / 1k benign | scams expected stopped in time | expected money saved | genuine_urgent_family interrupted |",
          "|---|---|---|---|---|---|"]
    for c in res["operating_curve"]:
        L.append(f"| {c['real_prior']:.1%} | {c['benign_interruptions_per_1k_sessions']} | {c['benign_holds_per_1k_sessions']} | "
                 f"{c['scams_expected_stopped_in_time_pct']}% | {c['expected_money_saved_pct']}% | {c['genuine_urgent_family_interrupted_pct']}% |")
    L += ["", "## Example decisions (full engine)", "",
          "Each example session is replayed alone with a fresh policy state, so per-user history from the full replay does "
          "not apply here.", "", "| typology | t (min) | amount | stage | p (real prior) | action | why |",
          "|---|---|---|---|---|---|---|"]
    for e in res["examples"]:
        if e["suppressed_by"]:
            why = f"suppressed: {e['suppressed_by']}"
        elif e.get("notify"):
            why = "; ".join(e["reasons"])
        else:
            why = ""  # no interruption, so no reasons to show
        L.append(f"| {e['typology']} | {e['ts_min']} | {e['amount']:.0f} | {e['stage_pred']} | {e['fused_p_real_prior']} | "
                 f"{e['action']} | {why} |")
    shown = next((e for e in res["examples"] if e["message_en"]), None)
    if shown:
        L += ["", f"Example message ({shown['typology']}, {shown['action']}):", "", f"- EN: {shown['message_en']}",
              f"- HI: {shown['message_hi']}"]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
