"""End-to-end evaluation of the payee-side stack on the synthetic ledger.

    python -m ml.campaign.evaluate                    # 10k sessions, writes ml/reports/campaign.{md,json}
    python -m ml.campaign.evaluate --n-sessions 20000 --save-model

Sections: (1) payee-risk model vs baselines and vs the simulator's label-derived stand-in, (2) benign
look-alikes, (3) campaign tracking and rupee-ranked cases, (4) how early money could have been stopped,
(5) the emerging-pattern radar on a scam that never appears in training.

Everything here is measured on synthetic data whose behaviours we wrote ourselves: it validates the
pipeline, not real-world accuracy. Assumed parameters are listed in the report.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .campaigns import CampaignTracker
from .features import FEATURES
from .ledger import DAY, HOUR
from .pipeline import SPLIT_DAYS, build
from .radar import Radar

REPORT_DIR = Path("ml/reports")
ACK_DELAY_S = 15 * 60          # analyst acts 15 minutes after a case opens (assumption)
COMPLAINT_MEDIAN_H = 24.0      # baseline: money is frozen ~a day after the first victim complaint (assumption)
ACCOUNT_FP_BUDGET = 0.02       # flag threshold: at most 2% of benign accounts ever flagged (valid period)
BENIGN_KINDS = ["merchant", "personal", "busy_merchant", "flash_merchant", "fundraiser", "rent_collector", "gig_worker", "payroll",
                "cashback_sender", "marketplace", "friend"]


def rec_at_fpr(y, s, fpr=0.01):
    thr = np.quantile(s[y == 0], 1 - fpr)
    return float((s[y == 1] >= thr).mean()), float(thr)


def metrics(y, s) -> dict:
    y, s = np.asarray(y), np.asarray(s, dtype="float64")
    if y.sum() == 0 or y.sum() == len(y):
        return {"n_pos": int(y.sum()), "n_neg": int((1 - y).sum())}
    return {"n_pos": int(y.sum()), "n_neg": int((1 - y).sum()), "roc_auc": round(roc_auc_score(y, s), 4),
            "pr_auc": round(average_precision_score(y, s), 4), "recall_at_1pct_fpr": round(rec_at_fpr(y, s)[0], 4)}


def model_section(c: pd.DataFrame, split) -> dict:
    te = c[c["day"] >= split[1]]
    train_accts = set(c.loc[c["day"] < split[0], "dst"])
    out = {"test_rows": len(te), "overall": metrics(te["y"], te["risk"])}
    subsets = {
        "cold start (first credit to the account)": te["log_life_credits"] == 0,
        "warm (>= 3 prior credits)": te["log_life_credits"] >= np.log1p(3),
        "accounts never seen in training (excl. novel)": ~te["dst"].isin(train_accts) & ~te["is_novel"],
        "layer-2/3 mule accounts (forwarded money)": te["kind"].eq("forward") | te["y"].eq(0),
    }
    for k, m in subsets.items():
        out[k] = metrics(te.loc[m, "y"], te.loc[m, "risk"])
    known = te[~te["is_novel"]]
    out["excluding the novel campaign"] = metrics(known["y"], known["risk"])
    for v, label in (("NOVEL_A", "novel A: wrong-credit return scam (never trained on)"), ("NOVEL_B", "novel B: micro-fee front, merchant-like (never trained on)")):
        nov = te[te["truth"].eq(v) | te["y"].eq(0)]
        out[label] = metrics(nov["truth"].eq(v).astype(int), nov["risk"])
    base = {"fan-in only (distinct payers 24h)": te["log_payers_24h"],
            "fan-in x fast pass-through": te["log_payers_24h"] * te["out_ratio_1h"],
            "account age only": -te["log_age_days"]}
    out["baselines"] = {k: metrics(te["y"], v) for k, v in base.items()}
    pay = te[te["kind"].isin(["scam_payment", "merchant", "p2p"])]
    yy = (pay["kind"] == "scam_payment").astype(int)
    out["payment_view"] = {"payer-side query rows": len(pay), "honest payee model": metrics(yy, pay["risk"]),
                           "old simulator stand-in (drawn from the label)": metrics(yy, pay["standin_score"])}
    return out


def wquantile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    o = np.argsort(x)
    cw = np.cumsum(w[o]) / w.sum()
    return float(x[o][min(len(x) - 1, int(np.searchsorted(cw, q)))])


def flag_threshold(c: pd.DataFrame, split, budget: float = ACCOUNT_FP_BUDGET) -> float:
    """Benign accounts only, scored out-of-fold (training period) or by the training model (validation period): the
    threshold above which at most ACCOUNT_FP_BUDGET of benign accounts *of each type* are ever flagged. Each account
    type gets equal weight, so busy merchants are not hidden by thousands of quiet personal accounts. Using the
    out-of-fold rows keeps the threshold honest for accounts the model has never seen."""
    v = c[(c["day"] >= 10) & (c["day"] < split[1]) & (c["y"] == 0)]
    g = v.groupby("dst").agg(r=("risk", "max"), k=("dst_kind", "first"))
    w = 1.0 / g.groupby("k")["r"].transform("size").to_numpy()
    return wquantile(g["r"].to_numpy(), w, 1 - budget)


def benign_section(c: pd.DataFrame, split, flag: float) -> dict:
    te = c[(c["day"] >= split[1]) & (c["y"] == 0)]
    oof = c[(c["day"] >= 10) & (c["day"] < split[0]) & (c["y"] == 0)]  # out-of-fold: accounts the scoring model never saw
    out = {}
    for k in BENIGN_KINDS:
        g, h = te[te["dst_kind"] == k], oof[oof["dst_kind"] == k]
        if len(g):
            out[k] = {"accounts": int(g["dst"].nunique()),
                      "accounts_ever_flagged_pct": round(100 * float((g.groupby("dst")["risk"].max() >= flag).mean()), 2),
                      "credits_flagged_pct": round(100 * float((g["risk"] >= flag).mean()), 3),
                      "unseen_accounts_ever_flagged_pct": round(100 * float((h.groupby("dst")["risk"].max() >= flag).mean()), 2) if len(h) else None}
    return out


def replay(b, flag: float, watch: float):
    """Replay the full ledger through the tracker with honest scores. Returns (tracker, alerts)."""
    ac = b.ledger.accounts
    tracker = CampaignTracker(dict(zip(ac["account"], ac["scoreable"])), watch=watch, flag=flag)
    tracker.mark_novel(ac.loc[ac["is_novel"], "account"])
    tr, c = b.ledger.transfers, b.credit
    risk = c["risk"].to_dict()
    reasoned = set()
    alerts = 0
    for i, (t, s, d, a) in enumerate(zip(tr["ts_s"].to_numpy(), tr["src"].to_numpy(), tr["dst"].to_numpy(), tr["amount"].to_numpy())):
        r = risk.get(i)
        why = None
        if r is not None and r >= flag:
            alerts += 1
            if d not in reasoned:
                reasoned.add(d)
                why = b.model.reasons(c.loc[i, FEATURES])
        tracker.observe(float(t), s, d, float(a), r, why)
    return tracker, alerts


def campaign_section(b, tracker: CampaignTracker, alerts: int, flag: float) -> dict:
    ac = b.ledger.accounts.set_index("account")
    end = float(b.ledger.transfers["ts_s"].max())
    cases = tracker.cases(end)
    truth = ac["campaign_truth"]
    rows, benign_only = [], 0
    for cs in cases:
        t = truth.reindex(cs.accounts)
        mules = ac["is_mule"].reindex(cs.accounts).to_numpy()
        top = t.dropna().value_counts()
        rows.append({"case": cs.case_id, "accounts": len(cs.accounts), "mule_share": float(mules.mean()),
                     "dominant_truth": None if top.empty else top.index[0],
                     "purity": float(top.iloc[0] / max(1, int(t.notna().sum()))) if not top.empty else 0.0, "novel": cs.novel})
        benign_only += int(mules.sum() == 0)
    syn = {k for k in truth.dropna().unique()}
    split_syn = {s: sum(1 for r in rows if r["dominant_truth"] == s) for s in syn}
    members = set(a for cs in cases for a in cs.accounts)
    mule_accts = set(ac.index[ac["is_mule"]]) & set(b.ledger.transfers["dst"])
    flagged_mules = mule_accts & members
    benign_members = [a for a in members if not ac.at[a, "is_mule"]]
    return {
        "flag_threshold": round(flag, 4), "credit_alerts": alerts, "accounts_flagged": len(tracker.flagged_ts),
        "watchlist_accounts": len(tracker.watchlist()), "cases": len(cases),
        "alerts_per_case": round(alerts / max(1, len(cases)), 1),
        "flagged_accounts_per_case": round(len(tracker.flagged_ts) / max(1, len(cases)), 1),
        "mule_accounts_in_cases_pct": round(100 * len(flagged_mules) / max(1, len(mule_accts)), 1),
        "benign_accounts_in_cases": len(benign_members),
        "cases_with_no_mule": benign_only,
        "mean_case_purity": round(float(np.mean([r["purity"] for r in rows if r["mule_share"] > 0])), 3) if any(r["mule_share"] > 0 for r in rows) else None,
        "cases_with_mules": sum(1 for r in rows if r["mule_share"] > 0),
        "syndicates_split_over_cases": {k: v for k, v in split_syn.items() if v > 1},
        "top_cases": [{"case": cs.case_id, "accounts": len(cs.accounts), "victims": cs.n_victims, "loss_in": round(cs.loss_in),
                       "recoverable": round(cs.recoverable), "risk": round(cs.risk, 3), "novel": cs.novel,
                       "reasons": cs.reasons} for cs in cases[:8]],
    }


def timeliness_section(b, tracker: CampaignTracker, seed: int = 5) -> dict:
    tr = b.ledger.transfers
    sc = tr[tr["scam_credit"]]
    known = sc[~sc["campaign_truth"].fillna("").str.startswith("NOVEL")]
    rng = np.random.default_rng(seed)

    def acted(a):
        if a not in tracker.parent:
            return np.inf
        root = tracker._find(a)
        return max(tracker.member_since[a], tracker.case_ts.get(root, np.inf)) + ACK_DELAY_S

    first = known.groupby("dst")["ts_s"].min()
    base = pd.Series({a: t + rng.lognormal(np.log(COMPLAINT_MEDIAN_H * HOUR), 0.8) for a, t in first.items()})
    ours = known["dst"].map(acted)
    after_ours = known["ts_s"] >= ours
    after_base = known["ts_s"] >= known["dst"].map(base)
    ac = b.ledger.accounts.set_index("account")
    lat, case_lat, pre = [], [], 0
    for s_, g in known.groupby("campaign_truth"):
        accts = ac.index[ac["campaign_truth"] == s_]
        t0 = g["ts_s"].min()
        f = [tracker.flagged_ts[a] for a in accts if a in tracker.flagged_ts]
        cs = [tracker.case_ts[tracker._find(a)] for a in accts if tracker.in_case(a)]
        if f:
            pre += int(min(f) <= t0)
            lat.append(max(0.0, min(f) - t0) / HOUR)
        if cs:
            case_lat.append(max(0.0, min(cs) - t0) / HOUR)
    val = known["amount"]
    return {
        "ack_delay_min": ACK_DELAY_S // 60, "complaint_baseline_median_h": COMPLAINT_MEDIAN_H,
        "scam_credit_value_arriving_after_action_pct": round(100 * float(val[after_ours].sum() / val.sum()), 1),
        "same_under_complaint_baseline_pct": round(100 * float(val[after_base].sum() / val.sum()), 1),
        "victim_payments_after_action_pct": round(100 * float(after_ours.mean()), 1),
        "same_under_complaint_baseline_payments_pct": round(100 * float(after_base.mean()), 1),
        "median_hours_first_victim_credit_to_first_flag": round(float(np.median(lat)), 1) if lat else None,
        "median_hours_first_victim_credit_to_case": round(float(np.median(case_lat)), 1) if case_lat else None,
        "syndicates_flagged": len(lat), "syndicates_with_case": len(case_lat), "syndicates_flagged_before_first_victim": pre,
        "syndicates_total": int(known["campaign_truth"].nunique()),
    }


def radar_section(b, flag: float, split, tracker: CampaignTracker) -> dict:
    s = b.snaps
    t_tr, t_va = split[0] * DAY, split[1] * DAY
    ref = s[s["ts_s"] < t_tr]
    grid = [0.99, 0.995, 0.997, 0.999]
    radar = Radar(quantile=0.997).fit(ref)
    z_ref = np.sort(radar.anomaly(ref))
    ac = b.ledger.accounts.set_index("account")
    variants = {v: set(ac.index[ac["campaign_truth"] == v]) for v in ("NOVEL_A", "NOVEL_B")}
    chosen, tried = None, []
    for q in grid:
        radar.threshold = float(np.quantile(z_ref, q))
        va = s[s["ts_s"] < t_va]
        em = radar.scan(va, va["risk"].to_numpy(), flag, start_ts=t_tr)
        tried.append({"quantile": q, "false_clusters_in_valid_15d": len(em)})
        if chosen is None and len(em) <= 2:
            chosen = q
    chosen = chosen or grid[-1]
    radar.threshold = float(np.quantile(z_ref, chosen))
    te = s[s["ts_s"] >= t_va]
    em = radar.scan(te, te["risk"].to_numpy(), flag, start_ts=t_va)
    all_nov = set().union(*variants.values())
    rows = []
    for e in em:
        kinds = pd.Series([ac.at[a, "kind"] for a in e.accounts]).value_counts().to_dict()
        rows.append({"cluster": e.cluster_id, "first_tick_h": round(e.first_ts / HOUR, 1),
                     "confirmed_h": None if e.confirmed_ts is None else round(e.confirmed_ts / HOUR, 1), "accounts": len(e.accounts),
                     "novel_purity": round(len(e.accounts & all_nov) / len(e.accounts), 2), "ticks": e.ticks, "kinds": kinds})
    tr = b.ledger.transfers
    te_all = s[s["ts_s"] >= t_va]
    z = radar.anomaly(te_all)
    truth_s = te_all["account"].map(ac["campaign_truth"]).to_numpy()
    benign_z = z[pd.isna(truth_s)]
    ranking = {}
    for v in variants:
        zv = z[truth_s == v]
        if len(zv) and len(benign_z):
            ranking[v] = {"snapshots": int(len(zv)), "anomaly_auc_vs_benign": round(float(roc_auc_score(np.r_[np.ones(len(zv)), np.zeros(len(benign_z))], np.r_[zv, benign_z])), 3),
                          "share_above_threshold_pct": round(100 * float((zv >= radar.threshold).mean()), 1)}
    out = {"anomaly_ranking": ranking, "reference_snapshots": len(ref), "chosen_quantile": chosen, "false_cluster_tuning_on_valid": tried, "test_clusters": rows,
           "false_clusters_in_test": sum(1 for r in rows if r["novel_purity"] < 0.5), "variants": {}}
    for v, accts in variants.items():
        victim = tr[(tr["campaign_truth"] == v) & tr["scam_credit"]]
        t0 = float(victim["ts_s"].min()) if len(victim) else None
        sup = sorted(tracker.flagged_ts[a] for a in accts if a in tracker.flagged_ts)
        k = min(4, len(sup))
        sup_t = sup[k - 1] if sup else None
        hits = [e for e in em if len(e.accounts & accts) / len(e.accounts) >= 0.6 and e.confirmed_ts is not None]
        rad_t = min((e.confirmed_ts for e in hits), default=None)

        def after(t, victim=victim):
            if t is None or not len(victim):
                return None
            return round(100 * float(victim.loc[victim["ts_s"] >= t + ACK_DELAY_S, "amount"].sum() / victim["amount"].sum()), 1)

        out["variants"][v] = {
            "accounts": len(accts), "first_victim_credit_h": None if t0 is None else round(t0 / HOUR, 1),
            "flagged_by_supervised_model": len(sup), "supervised_detect_h": None if sup_t is None else round(sup_t / HOUR, 1),
            "radar_detect_h": None if rad_t is None else round(rad_t / HOUR, 1),
            "victim_value_after_supervised_action_pct": after(sup_t), "victim_value_after_radar_action_pct": after(rad_t),
            "radar_accounts_covered": len(set().union(*(e.accounts & accts for e in hits))) if hits else 0}
    return out


def operating_curve(b, split, budgets=(0.005, 0.01, 0.02, 0.05)) -> list[dict]:
    """The real trade-off: how many false cases an analyst tolerates against how early campaigns are caught."""
    rows = []
    for bud in budgets:
        flag = flag_threshold(b.credit, split, bud)
        tracker, alerts = replay(b, flag, max(0.05, flag / 2))
        sec = campaign_section(b, tracker, alerts, flag)
        tim = timeliness_section(b, tracker)
        rows.append({"benign_account_fp_budget_pct": 100 * bud, "flag_threshold": round(flag, 3), "cases": sec["cases"],
                     "cases_with_mules": sec["cases_with_mules"], "cases_with_no_mule": sec["cases_with_no_mule"],
                     "mule_accounts_in_cases_pct": sec["mule_accounts_in_cases_pct"],
                     "median_h_first_victim_to_case": tim["median_hours_first_victim_credit_to_case"],
                     "scam_value_after_action_pct": tim["scam_credit_value_arriving_after_action_pct"]})
    return rows


def write_markdown(res: dict, path: Path) -> None:
    f = lambda d: " | ".join(str(d.get(k, "-")) for k in ("n_pos", "n_neg", "roc_auc", "pr_auc", "recall_at_1pct_fpr"))  # noqa: E731
    m, c, t, r = res["model"], res["campaigns"], res["timeliness"], res["radar"]
    L = ["# Payee-side campaign layer: synthetic ledger results", "",
         "> **Read this first.** The ledger is synthetic and every behaviour (mule speed, benign look-alikes, the novel scam) is an "
         "assumption we wrote. These numbers test that the pipeline works end to end and that its failure modes are visible; they are not "
         "real-world accuracy. Probabilities are at the ledger's mule prevalence, not at real-world prevalence.", "",
         f"Setup: {res['setup']}", "",
         "## 1. Payee-risk model (test period, days 75-90)", "",
         "| slice | positives | negatives | ROC-AUC | PR-AUC | recall @ 1% FPR |", "|---|---|---|---|---|---|",
         f"| all credits | {f(m['overall'])} |"]
    for k in ("cold start (first credit to the account)", "warm (>= 3 prior credits)", "accounts never seen in training (excl. novel)",
              "layer-2/3 mule accounts (forwarded money)", "excluding the novel campaign",
              "novel A: wrong-credit return scam (never trained on)", "novel B: micro-fee front, merchant-like (never trained on)"):
        L.append(f"| {k} | {f(m[k])} |")
    L += ["", "Baselines on all credits:", "", "| baseline | positives | negatives | ROC-AUC | PR-AUC | recall @ 1% FPR |", "|---|---|---|---|---|---|"]
    L += [f"| {k} | {f(v)} |" for k, v in m["baselines"].items()]
    pv = m["payment_view"]
    L += ["", f"Payer-side view ({pv['payer-side query rows']:,} payments: scam payments vs ordinary merchant/P2P payments):", "",
          "| score | positives | negatives | ROC-AUC | PR-AUC | recall @ 1% FPR |", "|---|---|---|---|---|---|",
          f"| honest payee model | {f(pv['honest payee model'])} |",
          f"| old simulator stand-in (drawn from the label) | {f(pv['old simulator stand-in (drawn from the label)'])} |", "",
          "## 2. Benign look-alikes (test period)", "",
          f"Flag threshold {res['campaigns']['flag_threshold']} (chosen on out-of-fold training rows plus the validation period so that at most {int(100 * ACCOUNT_FP_BUDGET)}% of benign accounts of each type are ever flagged).", "",
          "| account type | accounts (test) | ever flagged (test, accounts the model trained on) | credits flagged (test) | ever flagged (days 10-60, out-of-fold: accounts the model never saw) |", "|---|---|---|---|---|"]
    L += [f"| {k} | {v['accounts']} | {v['accounts_ever_flagged_pct']}% | {v['credits_flagged_pct']}% | {v['unseen_accounts_ever_flagged_pct']}% |" for k, v in res["benign"].items()]
    L += ["", "## 3. Campaigns and cases (whole ledger, honest scores)", "",
          f"- {c['credit_alerts']:,} credit-level alerts on {c['accounts_flagged']:,} flagged accounts became **{c['cases']} cases** "
          f"({c['alerts_per_case']} alerts and {c['flagged_accounts_per_case']} flagged accounts per case); {c['watchlist_accounts']:,} flagged accounts stayed on the watchlist because nothing corroborated them.",
          f"- {c['mule_accounts_in_cases_pct']}% of mule accounts that received money ended up inside a case; {c['benign_accounts_in_cases']} benign accounts were swept in; {c['cases_with_no_mule']} cases contained no mule at all.",
          f"- Mean purity of the {c['cases_with_mules']} cases that contain mules (share of accounts from the dominant ground-truth syndicate): {c['mean_case_purity']}. Syndicates split over several cases: {c['syndicates_split_over_cases'] or 'none'}.", "",
          "| case | accounts | victims | money in (₹) | still recoverable (₹) | risk | novel | why |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {x['case']} | {x['accounts']} | {x['victims']} | {x['loss_in']:,} | {x['recoverable']:,} | {x['risk']} | {x['novel']} | {'; '.join(x['reasons'])} |" for x in c["top_cases"]]
    L += ["", "## 4. How early could money have been stopped", "",
          "Operating curve: the flag threshold is set so that at most this share of benign accounts (per type) is ever flagged.", "",
          "| benign FP budget | flag threshold | cases | cases with mules | cases with no mule | mule accounts in cases | median hours, first victim credit to case | scam value arriving after action |",
          "|---|---|---|---|---|---|---|---|"]
    L += [f"| {x['benign_account_fp_budget_pct']:g}% | {x['flag_threshold']} | {x['cases']} | {x['cases_with_mules']} | {x['cases_with_no_mule']} | "
          f"{x['mule_accounts_in_cases_pct']}% | {x['median_h_first_victim_to_case']} | {x['scam_value_after_action_pct']}% |" for x in res["operating_curve"]]
    L += ["", "Default operating point (2%), used for sections 3 and 5:", "",
          f"Assumptions: the analyst acts {t['ack_delay_min']} minutes after a case opens; the baseline freezes an account about {t['complaint_baseline_median_h']:.0f} hours (lognormal) after its first victim credit.", "",
          "| | with case-driven action | complaint-driven baseline |", "|---|---|---|",
          f"| scam credit value that arrives after the account is acted on | {t['scam_credit_value_arriving_after_action_pct']}% | {t['same_under_complaint_baseline_pct']}% |",
          f"| victim payments that arrive after the account is acted on | {t['victim_payments_after_action_pct']}% | {t['same_under_complaint_baseline_payments_pct']}% |", "",
          f"Median time from a syndicate's first victim credit to its first flagged account: {t['median_hours_first_victim_credit_to_first_flag']} h; to its first case: {t['median_hours_first_victim_credit_to_case']} h. "
          f"{t['syndicates_flagged']}/{t['syndicates_total']} syndicates had a flagged account ({t['syndicates_flagged_before_first_victim']} before their first victim credit), {t['syndicates_with_case']}/{t['syndicates_total']} had a case.", "",
          "## 5. Emerging-pattern radar: two campaigns that never appear in training", "",
          "Both start on day 78 (test period). **A** is a debit-heavy 'wrong credit, please return' scam using aged accounts, irregular amounts and slow returns. "
          "**B** is a micro-fee front that deliberately looks like a busy small merchant. We authored both, so this is a stress test, not evidence that the radar works on real scams.", "",
          "| | accounts | first victim credit (h) | flagged by supervised model | supervised detect (h) | radar detect (h) | covered by radar | value after supervised action | value after radar action |",
          "|---|---|---|---|---|---|---|---|---|"]
    for v, x in r["variants"].items():
        L.append(f"| {v} | {x['accounts']} | {x['first_victim_credit_h']} | {x['flagged_by_supervised_model']} | {x['supervised_detect_h']} | {x['radar_detect_h']} | "
                 f"{x['radar_accounts_covered']} | {x['victim_value_after_supervised_action_pct']}% | {x['victim_value_after_radar_action_pct']}% |")
    L += ["", "Anomaly score on its own (does the radar rank the novel campaigns above ordinary accounts?):", "",
          "| campaign | snapshots | anomaly AUC vs benign | snapshots above the alert threshold |", "|---|---|---|---|"]
    L += [f"| {v} | {x['snapshots']} | {x['anomaly_auc_vs_benign']} | {x['share_above_threshold_pct']}% |" for v, x in r["anomaly_ranking"].items()]
    L += ["", f"Radar anomaly quantile {r['chosen_quantile']}, tuned on the validation period so it raises at most 2 clusters there ({r['false_cluster_tuning_on_valid']}). "
          f"Clusters in the test period that are not novel campaigns: {r['false_clusters_in_test']}.", "",
          "| cluster | first seen (h) | confirmed (h) | accounts | share that is a novel campaign | ticks | account types |", "|---|---|---|---|---|---|---|"]
    L += [f"| {x['cluster']} | {x['first_tick_h']} | {x['confirmed_h']} | {x['accounts']} | {x['novel_purity']} | {x['ticks']} | {x['kinds']} |" for x in r["test_clusters"]]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sessions", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--save-model", action="store_true")
    ap.add_argument("--no-radar", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    b = build(a.n_sessions, a.seed)
    c = b.credit
    split = b.split_days
    flag = flag_threshold(c, split)
    watch = max(0.05, flag / 2)
    tracker, alerts = replay(b, flag, watch)
    res = {"setup": f"{a.n_sessions:,} simulated sessions -> {len(b.ledger.transfers):,} transfers, {len(b.ledger.accounts):,} accounts; time split train < day {split[0]} <= valid < day {split[1]} <= test; flag {flag:.3f}, watch {watch:.3f}.",
           "model": model_section(c, split), "benign": benign_section(c, split, flag),
           "campaigns": campaign_section(b, tracker, alerts, flag), "timeliness": timeliness_section(b, tracker)}
    res["radar"] = radar_section(b, flag, split, tracker) if not a.no_radar else {}
    res["operating_curve"] = operating_curve(b, split)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "campaign.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    if not a.no_radar:
        write_markdown(res, REPORT_DIR / "campaign.md")
        print((REPORT_DIR / "campaign.md").read_text(encoding="utf-8"))
    if a.save_model:
        b.model.meta.update({"flag_threshold": flag, "watch_threshold": watch, "n_sessions": a.n_sessions})
        b.model.save()
        print("saved model to ml/campaign/artifacts")


if __name__ == "__main__":
    main()
