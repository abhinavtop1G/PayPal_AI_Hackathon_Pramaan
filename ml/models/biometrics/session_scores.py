"""Score every simulated touch window with the real biometrics model (BiLSTM + LDA fusion).

    python -m ml.models.biometrics.session_scores --sim data/sim_wf

Each BIO_WINDOW event carries a `bio_ref` (ml/sim/hmog_bank.py): the owner's held-out HMOG subject and the 10 real
gestures in the window. Every subject is enrolled once from its sessions 1-12; each window is scored against its
owner's profile, and the model's `behavioural_deviation` (threshold - fused similarity: > 0 means "not the enrolled
person") is written to the events table as `bio_model_dev`. The same scorer serves /v1/biometrics/verify and the session
API, so training and serving see identical scores.
"""
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ml.sim.hmog_bank import HmogBank

from .scorer import BioScorer

BATCH = 4096


def score_events(events: pd.DataFrame, scorer: BioScorer | None = None, bank: HmogBank | None = None) -> pd.Series:
    """bio_model_dev per event row (NaN where there is no touch window or no gesture reference)."""
    bank = bank or HmogBank.load()
    out = pd.Series(np.nan, index=events.index, dtype="float64")
    if bank is None or "bio_ref" not in events:
        return out
    refs = events["bio_ref"].dropna()
    if refs.empty:
        return out
    scorer = scorer or BioScorer()
    for s in bank.subjects:
        key = f"hmog:{s}"
        if key not in scorer.profiles:
            scorer.enroll(key, bank.enrolment(s))
    idx, vals = refs.index.to_numpy(), refs.to_numpy()
    for lo in range(0, len(vals), BATCH):
        res = [bank.resolve(r) for r in vals[lo:lo + BATCH]]
        out.loc[idx[lo:lo + BATCH]] = scorer.deviation_many([f"hmog:{o}" for o, _ in res], [g for _, g in res])
    return out


REPORT = Path("ml/reports/biometrics_in_sessions.md")


def write_report(ev: pd.DataFrame) -> str:
    """How the real model scores each simulated touch profile (share flagged = deviation > 0, i.e. 'not the owner')."""
    w = ev[ev["bio_model_dev"].notna() & ev["bio_ref"].notna()]
    prof = w["bio_ref"].str.split("|").str[4]
    g = w.groupby(prof)["bio_model_dev"]
    t = pd.DataFrame({"windows": g.size(), "mean_deviation": g.mean().round(3), "flagged_pct": (g.apply(lambda d: (d > 0).mean()) * 100).round(1)})
    order = [k for k in ("normal", "distracted", "rushed", "coerced", "remote") if k in t.index]
    L = ["# Real biometrics on simulated touch windows", "",
         "Every touch window in `data/sim_wf` is 10 real gestures from the customer's held-out HMOG subject (or, for `remote`, "
         "from a different subject), scored by the BiLSTM+LDA model against the customer's profile enrolled from sessions 1-12. "
         "Deviation > 0 means the window does not match the enrolled owner (the model's EER threshold).", "",
         "| profile | what it is | windows | mean deviation | flagged as not the owner |", "|---|---|---|---|---|"]
    what = {"normal": "own hands", "distracted": "own hands, mild documented shift", "rushed": "own hands, documented hurry shift",
            "coerced": "own hands, documented stress shift (assumption: HMOG has no coercion labels)",
            "remote": "someone else's real gestures (overlay / remote-control fraud)"}
    for k in order:
        r = t.loc[k]
        L.append(f"| {k} | {what[k]} | {int(r.windows):,} | {r.mean_deviation} | {r.flagged_pct}% |")
    L += ["", "The model recognises *who* is touching, not *how stressed* they are: it separates someone else's hands from the "
          "owner's, while modelled coercion barely moves it. Coercion is left to the stage tracker's own touch-rhythm inputs."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    return t.loc[order].to_string()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", type=Path, default=Path("data/sim_wf"))
    ap.add_argument("--report-only", action="store_true", help="only (re)write the report from existing scores")
    args = ap.parse_args()
    if args.report_only:
        print(write_report(pd.read_parquet(args.sim / "events.parquet")))
        return
    t0 = time.perf_counter()
    path = args.sim / "events.parquet"
    ev = pd.read_parquet(path)
    ev["bio_model_dev"] = score_events(ev)
    ev.to_parquet(path, index=False)
    n = int(ev["bio_model_dev"].notna().sum())
    print(f"scored {n:,} touch windows in {time.perf_counter() - t0:.1f}s -> {path} (bio_model_dev)")
    print(write_report(ev))


if __name__ == "__main__":
    main()
