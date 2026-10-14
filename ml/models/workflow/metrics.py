"""Decision-time evaluation: alerts can only fire at PAYMENT_ATTEMPT events (where the bank can
intervene), and a scam only counts as caught *in time* if the first alert comes at or before the
first extraction payment attempt.

Thresholds are chosen on valid so that a fixed share of benign sessions get a (false) alert, then
applied unchanged to test.
"""
import numpy as np
from sklearn.metrics import average_precision_score, f1_score

from .data import STAGES, SeqData

BUDGETS = (0.01, 0.02, 0.05)       # share of benign sessions that may receive a false alert
LOOKALIKES = ["hospital_emergency", "bank_app_update", "legit_investing", "genuine_urgent_family"]
REAL_PREVALENCE = 0.005            # for prevalence-adjusted precision (simulator uses 20% scams)


def first_alert(scores: list[np.ndarray], d: SeqData, thr: float):
    """Per session: index of the first payment attempt with score >= thr (or -1)."""
    out = np.full(len(scores), -1)
    for i, (s, pay) in enumerate(zip(scores, d.is_payment)):
        hit = np.flatnonzero(pay & (s >= thr))
        if len(hit):
            out[i] = hit[0]
    return out


def session_max(scores, d: SeqData) -> np.ndarray:
    return np.array([s[p].max() if p.any() else -np.inf for s, p in zip(scores, d.is_payment)])


def threshold_for_budget(scores, d: SeqData, budget: float) -> float:
    """Smallest threshold whose benign false-alert rate is <= budget."""
    m = session_max(scores, d)[~d.sessions["is_scam"].to_numpy()]
    return float(np.quantile(m[np.isfinite(m)], 1 - budget, method="higher")) + 1e-9


def alert_outcomes(scores, d: SeqData, thr: float) -> dict:
    s = d.sessions
    scam = s["is_scam"].to_numpy()
    idx = first_alert(scores, d, thr)
    alerted = idx >= 0
    ext_ts = s["extraction_ts"].to_numpy()
    alert_ts = np.array([d.ts[i][j] if j >= 0 else np.nan for i, j in enumerate(idx)])
    in_time = scam & alerted & (alert_ts <= ext_ts + 1e-6)
    # money saved: scam payments (non-'none' stage) at or after the alert are blocked
    saved, at_risk = 0.0, 0.0
    for i in np.flatnonzero(scam):
        pay = d.is_payment[i] & (d.stage[i] != STAGES.index("none"))
        at_risk += d.amount[i][pay].sum()
        if idx[i] >= 0:
            saved += d.amount[i][pay & (np.arange(len(pay)) >= idx[i])].sum()
    tpr = in_time.sum() / scam.sum()
    fpr = (alerted & ~scam).sum() / (~scam).sum()
    lead = (ext_ts - alert_ts)[in_time]
    return {
        "threshold": round(thr, 5),
        "benign_false_alert_rate": round(float(fpr), 4),
        "scams_caught_in_time": round(float(tpr), 4),
        "scams_caught_any_time": round(float((scam & alerted).sum() / scam.sum()), 4),
        "money_saved_pct": round(100 * saved / max(at_risk, 1e-9), 2),
        "precision_at_0.5pct_prevalence": round(float(tpr * REAL_PREVALENCE / max(tpr * REAL_PREVALENCE + fpr * (1 - REAL_PREVALENCE), 1e-12)), 4),
        "median_lead_time_min": round(float(np.median(lead) / 60), 1) if len(lead) else None,
        "in_time_by_typology": {t: round(float(in_time[(s["typology"] == t).to_numpy()].mean()), 3)
                                for t in sorted(s.loc[scam, "typology"].unique())},
        "false_alert_rate_lookalikes": {t: round(float(alerted[(s["typology"] == t).to_numpy()].mean()), 3)
                                        for t in LOOKALIKES if (s["typology"] == t).any()},
    }


def typology_accuracy(typ_pred: list[np.ndarray], d: SeqData) -> float:
    """Accuracy of the predicted workflow typology at each scam's first extraction payment attempt."""
    s = d.sessions
    hits = []
    for i in np.flatnonzero(s["is_scam"].to_numpy()):
        j = np.flatnonzero(d.is_payment[i] & (d.ts[i] >= s["extraction_ts"].iloc[i] - 1e-6))
        if len(j):
            hits.append(typ_pred[i][j[0]] == s["typology_id"].iloc[i])
    return round(float(np.mean(hits)), 4)


def evaluate(scores_va, d_va, scores_te, d_te, stage_pred_te=None, typ_pred_te=None) -> dict:
    out = {"payment_attempt_pr_auc": round(float(average_precision_score(
        np.concatenate([np.full(p.sum(), sc) for p, sc in zip(d_te.is_payment, d_te.sessions["is_scam"])]),
        np.concatenate([s[p] for s, p in zip(scores_te, d_te.is_payment)]))), 4)}
    for b in BUDGETS:
        out[f"budget_{b:.0%}"] = alert_outcomes(scores_te, d_te, threshold_for_budget(scores_va, d_va, b))
    if stage_pred_te is not None:
        scam = d_te.sessions["is_scam"].to_numpy()
        y = np.concatenate([st for st, sc in zip(d_te.stage, scam) if sc])
        p = np.concatenate([sp for sp, sc in zip(stage_pred_te, scam) if sc])
        out["stage_macro_f1_scam_sessions"] = round(float(f1_score(y, p, average="macro")), 4)
        out["stage_accuracy_scam_sessions"] = round(float((y == p).mean()), 4)
    if typ_pred_te is not None:
        out["typology_acc_at_first_extraction"] = typology_accuracy(typ_pred_te, d_te)
    return out
