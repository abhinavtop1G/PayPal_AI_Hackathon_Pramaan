"""Tabular baseline for AML: XGBoost on edge features + hand-built aggregates over the same causal
neighbourhood the GNN sees (last K events of each endpoint, strictly before the edge).

    python -m ml.models.gnn.baseline --k 32

If the GNN can't beat this, the attention isn't earning its keep.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import xgboost as xgb

from .data import EDGE_NUM_NAMES, load_aml
from .sampler import OUT, TemporalNeighborSampler
from .train import best_f1_threshold, metrics

REPORT_DIR = Path("ml/reports")


@torch.no_grad()
def neighbourhood_features(g, k: int, device, bs: int = 200_000) -> tuple[np.ndarray, list[str]]:
    src, dst, t = (torch.as_tensor(a, device=device) for a in (g.src, g.dst, g.t))
    amt = torch.as_tensor(g.x_num[:, 0], device=device)
    sampler = TemporalNeighborSampler(src, dst, g.n_nodes, k)
    names, blocks = [], []
    for side, nodes_all in (("u", src), ("v", dst)):
        names += [f"{side}_{n}" for n in ["log_n_prior", "n_1h", "n_24h", "frac_out", "amt_mean", "amt_max",
                                          "amt_min", "amt_now_vs_mean", "dt_last_min", "n_distinct_cp", "n_valid"]]
        parts = []
        for i in range(0, g.n_edges, bs):
            ids = torch.arange(i, min(i + bs, g.n_edges), device=device)
            nodes = nodes_all[ids]
            nb, d, m, n_prior = sampler.sample(nodes, ids)
            mf = m.float()
            cnt = mf.sum(1).clamp(min=1)
            dt = (t[ids][:, None] - t[nb]).float()
            a = amt[nb]
            cp = torch.where(d == OUT, dst[nb], src[nb]).masked_fill(~m, -1)  # counterpart account
            cp_sorted = cp.sort(1).values
            distinct = ((cp_sorted[:, 1:] != cp_sorted[:, :-1]) & (cp_sorted[:, 1:] >= 0)).sum(1) + (cp_sorted[:, 0] >= 0).long()
            mean_a = (a * mf).sum(1) / cnt
            last_dt = torch.where(m[:, -1], dt[:, -1], torch.full_like(dt[:, -1], float("nan")))
            parts.append(torch.stack([
                torch.log1p(n_prior.float()),
                ((dt <= 60) & m).sum(1).float(),
                ((dt <= 1440) & m).sum(1).float(),
                ((d == OUT) & m).sum(1).float() / cnt,
                mean_a,
                a.masked_fill(~m, -1e9).max(1).values.masked_fill(~m.any(1), float("nan")),
                a.masked_fill(~m, 1e9).min(1).values.masked_fill(~m.any(1), float("nan")),
                amt[ids] - mean_a,
                last_dt,
                distinct.float(),
                mf.sum(1),
            ], 1).cpu())
        blocks.append(torch.cat(parts).numpy())
    return np.concatenate(blocks, 1), names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=32)
    args = ap.parse_args()
    device = torch.device("cuda")
    t0 = time.time()
    g = load_aml()
    tr, va, te = g.splits()
    nb, nb_names = neighbourhood_features(g, args.k, device)
    X = np.concatenate([g.x_num, np.column_stack([g.cur_paid, g.cur_recv, g.fmt]).astype("float32"), nb], 1)
    names = EDGE_NUM_NAMES + ["cur_paid", "cur_recv", "fmt"] + nb_names
    print(f"features {X.shape} in {time.time() - t0:.0f}s")

    model = xgb.XGBClassifier(
        n_estimators=3000, learning_rate=0.05, max_depth=8, subsample=0.8, colsample_bytree=0.6,
        scale_pos_weight=10.0, tree_method="hist", device="cuda", eval_metric="aucpr",
        early_stopping_rounds=200, random_state=0,
    )
    t1 = time.time()
    model.fit(X[tr], g.y[tr], eval_set=[(X[va], g.y[va])], verbose=500)
    p_va, p_te = model.predict_proba(X[va])[:, 1], model.predict_proba(X[te])[:, 1]
    thr = best_f1_threshold(g.y[va], p_va)
    imp = model.get_booster().get_score(importance_type="gain")
    top = sorted(((names[int(k[1:])], round(v, 1)) for k, v in imp.items()), key=lambda x: -x[1])[:15]
    res = {"model": "xgb_neighbourhood", "k": args.k, "best_iteration": int(model.best_iteration),
           "train_seconds": round(time.time() - t1), "valid": metrics(g.y[va], p_va, thr),
           "test": metrics(g.y[te], p_te, thr), "top_gain_features": top}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "gnn_aml_xgb_baseline.json").write_text(json.dumps(res, indent=2, default=float))
    print(f"TEST {res['test']}\ntop features {top[:8]}")


if __name__ == "__main__":
    main()
