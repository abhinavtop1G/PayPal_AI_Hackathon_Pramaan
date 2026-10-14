"""What does each new signal add? Refit fusion with one input swapped or removed and replay the test period.

    python -m ml.engine.ablation        # after oof + fit; writes ml/reports/ablation.{md,json}

Variants (same GRU scores, same data, same policy; only the fusion inputs change):
    full                 real HMOG biometrics model + telecom caller reputation (what ships)
    stand-in biometrics  touch deviation from the five summary numbers (what shipped before)
    no touch signal      bio_dev = 0
    no telecom signal    caller_reported_active = 0
The fusion model is refitted for each variant on the same rows (out-of-fold training period + valid half A).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from ml.models.workflow.data import BIO, load

from .components import build_tables
from .fusion import FusionModel
from .oof import OUT as OOF
from .policy import AlertPolicy
from .simulate import outcomes, replay

REPORT = Path("ml/reports/ablation")


def standin_dev(d) -> dict:
    """(session_id, event_idx) -> the older stand-in deviation: RMS of the five summary log-ratios, carried forward."""
    col = {n: i for i, n in enumerate(d.num_names)}
    bio = [col[f"bio_{k}_vs_base"] for k in BIO]
    out = {}
    for i, x in enumerate(d.num):
        has = x[:, col["has_bio"]] > 0
        dev = pd.Series(np.where(has, np.sqrt((x[:, bio] ** 2).mean(1)), np.nan)).ffill().fillna(0).to_numpy()
        sid = d.sessions["session_id"].iloc[i]
        for j in np.flatnonzero(d.is_payment[i]):
            out[(sid, int(j))] = float(dev[j])
    return out


def variant(t: pd.DataFrame, name: str, lookup: dict) -> pd.DataFrame:
    t = t.copy()
    if name == "stand-in biometrics":
        t["bio_dev"] = [lookup[(s, int(e))] for s, e in zip(t["session_id"], t["event_idx"])]
    elif name == "no touch signal":
        t["bio_dev"] = 0.0
    elif name == "no telecom signal":
        t["caller_reported_active"] = 0.0
    return t


def main():
    data = load()
    look = {}
    for part in ("train", "valid", "test"):
        look |= standin_dev(data[part])
    T = build_tables()
    tv, dv = T["valid"]
    tt, _ = T["test"]
    cut = dv.sessions["start_time"].median()
    tA = tv[tv["session_idx"].isin(np.flatnonzero(dv.sessions["start_time"] < cut))]
    oof = pd.read_parquet(OOF)
    res = {}
    for name in ("full", "stand-in biometrics", "no touch signal", "no telecom signal"):
        fit_rows = pd.concat([variant(oof, name, look), variant(tA, name, look)])
        f = FusionModel(real_prior=0.005).fit(fit_rows)
        te = variant(tt, name, look)
        te = te.assign(fused_p=f.proba(te))
        pol = AlertPolicy()

        def decide(r, pol=pol):
            dec = pol.decide(r, r["fused_p"], r["start_time"] + pd.Timedelta(seconds=r["ts"]))
            return dec.action, dec.notify
        o = outcomes(replay(te, decide))
        fake_kyc = te[te["typology"].isin(["fake_kyc_apk", "bank_app_update"])]
        res[name] = {
            "payment_pr_auc": round(float(average_precision_score(te["in_progress"], te["fused_p"])), 4),
            "fake_kyc_vs_lookalike_pr_auc": round(float(average_precision_score(fake_kyc["in_progress"], fake_kyc["fused_p"])), 4),
            "gain_bio_dev": f.importance().get("bio_dev"), "gain_caller_reported": f.importance().get("caller_reported_active"),
            **{k: o[k] for k in ("scams_expected_stopped_in_time_pct", "expected_money_saved_pct",
                                 "benign_interruptions_per_1k_sessions", "benign_holds_per_1k_sessions")},
            "lookalike_interrupted_pct": o["lookalike_interrupted_pct"],
        }
        print(name, res[name])
    REPORT.with_suffix(".json").write_text(json.dumps(res, indent=2))
    L = ["# Ablation: what the real biometrics model and the telecom signal add", "",
         "Same GRU scores, same simulated test period, same alert policy (full, 0.5% real-world prior); fusion refitted per "
         "variant on the same rows. Simulator data: the signals' effect depends on our assumptions about how often scam "
         "numbers are already reported and how often fraud happens on someone else's hands (overlay / remote-control apps).", "",
         "| variant | payment PR-AUC | fake-KYC vs bank-update PR-AUC | scams stopped in time | money saved | genuine interruptions / 1k | genuine holds / 1k | fusion gain: touch / caller reported |",
         "|---|---|---|---|---|---|---|---|"]
    for k, r in res.items():
        L.append(f"| {k} | {r['payment_pr_auc']} | {r['fake_kyc_vs_lookalike_pr_auc']} | {r['scams_expected_stopped_in_time_pct']}% | "
                 f"{r['expected_money_saved_pct']}% | {r['benign_interruptions_per_1k_sessions']} | {r['benign_holds_per_1k_sessions']} | "
                 f"{r['gain_bio_dev']} / {r['gain_caller_reported']} |")
    L += ["", "Look-alike sessions interrupted (%): " + "; ".join(f"**{k}** {r['lookalike_interrupted_pct']}" for k, r in res.items())]
    REPORT.with_suffix(".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}.md")


if __name__ == "__main__":
    main()
