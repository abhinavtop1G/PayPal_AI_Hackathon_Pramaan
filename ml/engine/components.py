"""Component scores at every payment attempt — the contract between detectors and the alert engine.

Each row is one PAYMENT_ATTEMPT (the point where the bank can intervene) with:
  gru_p            workflow GRU: P(scam in progress)          [models/workflow]
  gru_stage        workflow GRU: argmax stage
  typ_*            workflow GRU: typology probabilities
  mule_score       payee intelligence: the payee-side model's risk for the receiving account (ml/campaign, via attach)
  bio_dev          behavioural deviation: the real HMOG biometrics model's score for the latest touch window
                   (RAKSHAM_BIO_SOURCE=standin: the older summary-statistics stand-in, kept for the ablation)
  caller_reported_active  on a call with a number the telecom has on its reported list (PSI, consented)
  log_amt_vs_avg   amount vs the user's average
  payee_is_new, payee_known_trusted, unknown_call_active  context flags
plus labels/metadata for evaluation (in_progress, is_scam, typology, extraction_ts, amount, ...).

The temporal GNN (IBM-AML) and the IEEE-CIS models stay standalone: their feature spaces don't exist in UPI
sessions. HMOG does: simulated touch windows carry real gestures from held-out HMOG subjects.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from ml.models.workflow.data import BIO, STAGES, TYPOLOGIES, SeqData, load
from ml.models.workflow.model import WorkflowGRU
from ml.models.workflow.train import pad_batch

GRU_CKPT = Path(os.environ.get("RAKSHAM_GRU_CKPT", "ml/models/workflow/artifacts/workflow_gru.pt"))
BIO_SOURCE = os.environ.get("RAKSHAM_BIO_SOURCE", "model")  # "model" (real HMOG scorer) | "standin" (ablation)


def default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"
SCAM_TYPS = TYPOLOGIES[:4]


def subset(d: SeqData, idx: np.ndarray) -> SeqData:
    pick = lambda xs: [xs[i] for i in idx]  # noqa: E731
    return SeqData(pick(d.num), pick(d.cat), pick(d.stage), pick(d.is_payment), pick(d.ts), pick(d.amount),
                   d.sessions.iloc[idx].reset_index(drop=True), d.num_names)


def load_gru(device=None) -> WorkflowGRU:
    device = device or default_device()
    ck = torch.load(GRU_CKPT, weights_only=False, map_location=device)
    sd = ck["state_dict"]
    m = WorkflowGRU(len(ck["num_names"]), sd["mean"], sd["std"], d=ck["args"]["d"], dropout=ck["args"]["dropout"])
    m.load_state_dict(sd)
    return m.to(device).eval()


@torch.no_grad()
def gru_outputs(model, d: SeqData, device=None, bs: int = 1024):
    device = device or default_device()
    """Per session: (p_scam [T], stage [T], typology probs [T, C])."""
    out = []
    for s in range(0, len(d.num), bs):
        idx = np.arange(s, min(s + bs, len(d.num)))
        num, cat, *_ = pad_batch(d, idx, device)
        a, b, c = model(num, cat)
        a, b, c = torch.sigmoid(a).cpu().numpy(), b.argmax(-1).cpu().numpy(), torch.softmax(c, -1).cpu().numpy()
        for r, i in enumerate(idx):
            n = len(d.num[i])
            out.append((a[r, :n], b[r, :n], c[r, :n]))
    return out


def component_table(d: SeqData, gru_out) -> pd.DataFrame:
    names = d.num_names
    col = {n: i for i, n in enumerate(names)}
    bio_cols = [col[f"bio_{k}_vs_base"] for k in BIO]
    rows = []
    s = d.sessions
    for i in range(len(d.num)):
        x, c, pay = d.num[i], d.cat[i], d.is_payment[i]
        p, st, ty = gru_out[i]
        # latest biometric window at or before each event (behavioural deviation)
        has_bio = x[:, col["has_bio"]] > 0
        if BIO_SOURCE == "model" and "bio_model_dev" in col:
            dev = np.where(has_bio, x[:, col["bio_model_dev"]], np.nan)
        else:
            dev = np.where(has_bio, np.sqrt((x[:, bio_cols] ** 2).mean(1)), np.nan)
        dev = pd.Series(dev).ffill().fillna(0).to_numpy()
        reported = x[:, col["caller_reported"]] if "caller_reported" in col else np.zeros(len(x), "float32")
        for j in np.flatnonzero(pay):
            rows.append({
                "session_idx": i, "event_idx": int(j), "session_id": s["session_id"].iloc[i], "user_id": s["user_id"].iloc[i],
                "start_time": s["start_time"].iloc[i], "ts": d.ts[i][j], "amount": d.amount[i][j],
                "gru_p": float(p[j]), "gru_stage": STAGES[int(st[j])],
                **{f"typ_{t}": float(ty[j, k]) for k, t in enumerate(TYPOLOGIES)},
                "mule_score": float(x[j, col["mule_score"]]), "bio_dev": float(dev[j]),
                "log_amt_vs_avg": float(x[j, col["log_amt_vs_avg"]]), "payee_is_new": float(x[j, col["payee_is_new"]]),
                "payee_is_merchant": float(x[j, col["payee_is_merchant"]]),
                "unknown_call_active": float(x[j, col["call_active"]] > 0 and c[j, 1] >= 2),
                "caller_reported_active": float(x[j, col["call_active"]] > 0 and reported[j] > 0),
                "log_call_min": float(x[j, col["log_call_min"]]),
                "in_progress": int(d.stage[i][j] != STAGES.index("none")),
                "is_scam": bool(s["is_scam"].iloc[i]), "typology": s["typology"].iloc[i],
                "extraction_ts": s["extraction_ts"].iloc[i],
            })
    t = pd.DataFrame(rows)
    t["payee_known_trusted"] = ((t["payee_is_new"] == 0) & (t["mule_score"] < 0.3)).astype(float)
    t["pred_typology"] = t[[f"typ_{x}" for x in TYPOLOGIES]].to_numpy().argmax(1)
    t["pred_typology"] = [TYPOLOGIES[k] for k in t["pred_typology"]]
    return t


def build_tables(device=None) -> dict[str, tuple[pd.DataFrame, SeqData]]:
    device = device or default_device()
    data = load()
    model = load_gru(device)
    return {k: (component_table(data[k], gru_outputs(model, data[k], device)), data[k]) for k in ("valid", "test")}
