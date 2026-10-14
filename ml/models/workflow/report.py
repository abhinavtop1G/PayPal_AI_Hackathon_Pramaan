"""Aggregate workflow GRU seeds + baselines into reports/workflow.md.

    python -m ml.models.workflow.report
"""
import json
import sys
from pathlib import Path

import numpy as np

from .metrics import LOOKALIKES

REPORT_DIR = Path("ml/reports")


def _ms(vals, pct=False):
    v = np.asarray(vals, float) * (100 if pct else 1)
    f = "{:.1f}" if pct else "{:.3f}"
    return f.format(v.mean()) + (f" ± {f.format(v.std(ddof=1))}" if len(v) > 1 else "")


def main():
    gru = [json.loads(p.read_text()) for p in sorted(REPORT_DIR.glob("workflow_gru_s*.json"))]
    base = json.loads((REPORT_DIR / "workflow_baselines.json").read_text())
    xgb = base["xgb_bag_of_events"]
    rule = base["rule"]["budget_n/a"]
    rows = [("Workflow GRU", gru), ("XGBoost bag-of-events", [xgb])]

    lines = [
        "# Workflow sequence model — simulator sessions",
        "",
        "50k simulated sessions (20% scams, incl. legitimate look-alikes of each scam workflow); split by "
        "session start: days 0–60 train, 60–75 valid, 75–90 test (voice-clone share of scams rises 17% → 29%). "
        "Alerts may only fire at payment attempts; *in time* = at or before the first extraction payment. "
        "Thresholds set on valid for a benign false-alert budget, applied unchanged to test.",
        "",
        "> **Caveat:** the simulator is near-separable for scam-vs-benign (both models catch ≈99–100% of scams in "
        "time). These numbers validate the pipeline, not real-world accuracy. The informative comparisons are "
        "stage tracking and false alerts on look-alike sessions.",
        "",
        "## Stage tracking and typology",
        "",
        "| model | stage macro-F1 (scam sessions) | stage accuracy | typology acc. at first extraction | payment-attempt PR-AUC |",
        "|---|---|---|---|---|",
    ]
    for name, rs in rows:
        lines.append(f"| {name} ({len(rs)} seed{'s' if len(rs) > 1 else ''}) | "
                     f"{_ms([r['stage_macro_f1_scam_sessions'] for r in rs])} | {_ms([r['stage_accuracy_scam_sessions'] for r in rs])} | "
                     f"{_ms([r['typology_acc_at_first_extraction'] for r in rs])} | {_ms([r['payment_attempt_pr_auc'] for r in rs])} |")
    for budget in ("budget_1%", "budget_5%"):
        lines += ["", f"## Alerting at a {budget.split('_')[1]} benign false-alert budget", "",
                  "| model | benign FA rate | scams caught in time | money saved % | "
                  + " | ".join(f"FA: {t}" for t in LOOKALIKES) + " |",
                  "|---|---|---|---|" + "---|" * len(LOOKALIKES)]
        for name, rs in rows:
            b = [r[budget] for r in rs]
            lines.append(f"| {name} | {_ms([x['benign_false_alert_rate'] for x in b], True)}% | "
                         f"{_ms([x['scams_caught_in_time'] for x in b], True)}% | {_ms([x['money_saved_pct'] / 100 for x in b], True)}% | "
                         + " | ".join(f"{_ms([x['false_alert_rate_lookalikes'][t] for x in b], True)}%" for t in LOOKALIKES) + " |")
    lines += ["", f"Naive rule (unknown caller + new payee): benign FA {100 * rule['benign_false_alert_rate']:.1f}%, "
              f"scams caught in time {100 * rule['scams_caught_in_time']:.1f}% "
              f"(misses all fake-KYC and investment scams: {rule['in_time_by_typology']})."]
    (REPORT_DIR / "workflow.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
