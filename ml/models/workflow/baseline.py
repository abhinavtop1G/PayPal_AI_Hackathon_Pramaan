"""Non-sequential baselines for the workflow detector, scored with the same decision-time protocol.

    python -m ml.models.workflow.baseline

  rule  - alert when paying a new payee while on a call with an unknown / VoIP number
  xgb   - XGBoost on causal bag-of-events features: current event + cumulative event-type counts +
          "ever happened" flags so far in the session (no order information beyond that)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from .data import CAT_COLS, EVENTS, STAGES, SeqData, load
from .metrics import alert_outcomes, evaluate

REPORT_DIR = Path("ml/reports")
EVER = ["call_active", "screen_share_active", "sideloaded_app_present", "accessibility_granted", "sms_has_link"]


def bag_of_events(d: SeqData) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rows = all events; returns (X, y_in_progress, session_index)."""
    num = np.concatenate(d.num)
    cat = np.concatenate(d.cat)
    sess = np.concatenate([np.full(len(x), i) for i, x in enumerate(d.num)])
    names = d.num_names
    counts = pd.get_dummies(pd.Categorical(cat[:, 0], categories=range(len(EVENTS)))).astype("float32")
    counts = counts.groupby(sess).cumsum().to_numpy()
    ever = pd.DataFrame(num[:, [names.index(c) for c in EVER]]).groupby(sess).cummax().to_numpy()
    unknown_call = ((cat[:, 1] >= 2) & (num[:, names.index("call_active")] > 0)).astype("float32")
    ever_unknown_call = pd.Series(unknown_call).groupby(sess).cummax().to_numpy()[:, None]
    onehots = [np.eye(len(v), dtype="float32")[cat[:, j]] for j, v in enumerate(CAT_COLS.values())]
    X = np.concatenate([num, *onehots, counts, ever, ever_unknown_call], 1)
    y = (np.concatenate(d.stage) != STAGES.index("none")).astype(int)
    return X, y, sess


def split_scores(flat: np.ndarray, d: SeqData) -> list[np.ndarray]:
    return np.split(flat, np.cumsum([len(x) for x in d.num])[:-1])


def rule_scores(d: SeqData) -> list[np.ndarray]:
    n = d.num_names
    return [((x[:, n.index("call_active")] > 0) & (c[:, 1] >= 2) & (x[:, n.index("payee_is_new")] > 0)).astype(float)
            for x, c in zip(d.num, d.cat)]


def main():
    data = load()
    res = {"rule": {"budget_n/a": alert_outcomes(rule_scores(data["test"]), data["test"], 0.5)}}

    Xtr, ytr, _ = bag_of_events(data["train"])
    Xva, yva, _ = bag_of_events(data["valid"])
    Xte, _, _ = bag_of_events(data["test"])
    model = xgb.XGBClassifier(n_estimators=3000, learning_rate=0.05, max_depth=6, subsample=0.8, colsample_bytree=0.8,
                              tree_method="hist", device="cuda", eval_metric="aucpr", early_stopping_rounds=200)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=0)
    p_va = split_scores(model.predict_proba(Xva)[:, 1], data["valid"])
    p_te = split_scores(model.predict_proba(Xte)[:, 1], data["test"])

    # same features, multiclass heads for stage tracking and workflow typology
    def multiclass(y_tr, y_va):
        m = xgb.XGBClassifier(n_estimators=2000, learning_rate=0.08, max_depth=6, subsample=0.8, colsample_bytree=0.8,
                              tree_method="hist", device="cuda", eval_metric="mlogloss", early_stopping_rounds=100)
        m.fit(Xtr, y_tr, eval_set=[(Xva, y_va)], verbose=0)
        return split_scores(m.predict_proba(Xte).argmax(1), data["test"])

    stage_te = multiclass(np.concatenate(data["train"].stage), np.concatenate(data["valid"].stage))
    typ = lambda d: np.concatenate([np.full(len(x), t) for x, t in zip(d.num, d.sessions["typology_id"])])  # noqa: E731
    typ_te = multiclass(typ(data["train"]), typ(data["valid"]))
    res["xgb_bag_of_events"] = {"best_iteration": int(model.best_iteration),
                                **evaluate(p_va, data["valid"], p_te, data["test"], stage_te, typ_te)}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "workflow_baselines.json").write_text(json.dumps(res, indent=2, default=float))
    for name, r in res.items():
        for k, v in r.items():
            if isinstance(v, dict):
                print(f"{name:18s} {k:11s} FA {v['benign_false_alert_rate']:.3f}  in-time {v['scams_caught_in_time']:.3f}  "
                      f"saved {v['money_saved_pct']:.1f}%  prec@0.5% {v['precision_at_0.5pct_prevalence']:.3f}  "
                      f"by-typology {v['in_time_by_typology']}")


if __name__ == "__main__":
    main()
