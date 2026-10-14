"""Aggregate GNN seed runs + XGB baseline into reports/gnn_aml.md.

    python -m ml.models.gnn.report
"""
import json
import sys
from pathlib import Path

import numpy as np

REPORT_DIR = Path("ml/reports")
KEYS = ["f1", "precision", "recall", "pr_auc", "roc_auc"]


def _fmt(vals):
    vals = np.asarray(vals, dtype=float)
    return f"{vals.mean():.4f}" if len(vals) == 1 else f"{vals.mean():.4f} ± {vals.std(ddof=1):.4f}"


def main():
    rows = []
    for attn in ["diff", "vanilla"]:
        runs = [json.loads(p.read_text()) for p in sorted(REPORT_DIR.glob(f"gnn_aml_{attn}_s*.json"))]
        if runs:
            rows.append((f"Temporal GNN, {attn} attention", len(runs), {k: [r["test"][k] for r in runs] for k in KEYS},
                         {"valid_f1": [r["valid"]["f1"] for r in runs], "params": runs[0]["params"],
                          "lambda": [r["history"][r["best_epoch"]]["lambda"] for r in runs]}))
    base = REPORT_DIR / "gnn_aml_xgb_baseline.json"
    if base.exists():
        b = json.loads(base.read_text())
        rows.append(("XGBoost + neighbourhood aggregates", 1, {k: [b["test"][k]] for k in KEYS},
                     {"valid_f1": [b["valid"]["f1"]]}))

    lines = [
        "# IBM AML HI-Small — laundering transaction detection",
        "",
        "Chronological 60/20/20 edge split (test = latest 20% of transactions, laundering rate 0.177% vs 0.075% "
        "in train). Each model sees only events strictly before the scored transaction. Threshold maximises "
        "valid minority-class F1; metrics below are on test (mean ± std over seeds).",
        "",
        "| model | seeds | test F1 | precision | recall | PR-AUC | ROC-AUC | valid F1 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, n, m, extra in rows:
        lines.append(f"| {name} | {n} | " + " | ".join(_fmt(m[k]) for k in KEYS) + f" | {_fmt(extra['valid_f1'])} |")
    lam = [r for r in rows if "lambda" in r[3] and r[3]["lambda"][0] is not None]
    if lam:
        lines += ["", f"Learned differential-attention λ at the selected epoch: {_fmt(lam[0][3]['lambda'])}."]
    (REPORT_DIR / "gnn_aml.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252 (no λ / ±)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
