"""Train the temporal GNN on IBM AML HI-Small (edge-level laundering classification).

    python -m ml.models.gnn.train --attn diff vanilla          # ablation, same seed/budget
    python -m ml.models.gnn.train --attn diff --epochs 1 --max-steps 50   # dry run

Each epoch: all positive train edges + a fresh random `--neg-frac` of negatives. Model selection on
valid PR-AUC; the decision threshold maximises valid minority-class F1 and is then applied to test.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score

from .data import EDGE_NUM_NAMES, load_aml
from .model import TemporalEdgeModel
from .sampler import IN, OUT, TemporalNeighborSampler

CKPT_DIR = Path("checkpoints/gnn")
REPORT_DIR = Path("ml/reports")


class EdgeData:
    """All edge tensors on device + batch assembly."""

    def __init__(self, g, device, k):
        to = lambda a: torch.as_tensor(a, device=device)  # noqa: E731
        self.src, self.dst, self.t = to(g.src), to(g.dst), to(g.t)
        self.x_num, self.cur_paid, self.cur_recv, self.fmt = to(g.x_num), to(g.cur_paid), to(g.cur_recv), to(g.fmt)
        self.y = to(g.y).float()
        self.sampler = TemporalNeighborSampler(self.src, self.dst, g.n_nodes, k)

    def enc(self, model, ids):
        return model.edge_enc(self.x_num[ids], self.cur_paid[ids], self.cur_recv[ids], self.fmt[ids])

    def batch(self, model, ids: torch.Tensor) -> dict:
        out = {"edge_emb": self.enc(model, ids)}
        b = len(ids)
        for side, nodes, role in (("u", self.src[ids], OUT), ("v", self.dst[ids], IN)):
            nb, d, mask, n_prior = self.sampler.sample(nodes, ids)
            k = nb.shape[1]
            out[f"nb_emb_{side}"] = self.enc(model, nb.reshape(-1)).view(b, k, -1)
            out[f"dt_{side}"] = (self.t[ids][:, None] - self.t[nb]).masked_fill(~mask, 0)
            out[f"dir_{side}"], out[f"mask_{side}"], out[f"n_{side}"] = d, mask, n_prior
            out[f"role_{side}"] = torch.full((b,), role, device=ids.device)
        return out


@torch.no_grad()
def predict(model, data: EdgeData, ids: np.ndarray, bs: int) -> np.ndarray:
    model.eval()
    out = []
    for i in range(0, len(ids), bs):
        idx = torch.as_tensor(ids[i:i + bs], device=data.y.device)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out.append(torch.sigmoid(model(data.batch(model, idx)).float()).cpu())
    return torch.cat(out).numpy()


def best_f1_threshold(y, p) -> float:
    grid = np.unique(np.quantile(p, np.linspace(0.95, 0.99995, 400)))
    f1 = [f1_score(y, p >= t, zero_division=0) for t in grid]
    return float(grid[int(np.argmax(f1))])


def metrics(y, p, thr) -> dict:
    pred = p >= thr
    return {
        "pr_auc": round(average_precision_score(y, p), 4),
        "roc_auc": round(roc_auc_score(y, p), 4),
        "f1": round(f1_score(y, pred, zero_division=0), 4),
        "precision": round(precision_score(y, pred, zero_division=0), 4),
        "recall": round(recall_score(y, pred, zero_division=0), 4),
        "threshold": round(thr, 5),
    }


def run(attn: str, g, args, device) -> dict:
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    tr, va, te = g.splits()
    data = EdgeData(g, device, args.k)
    x_tr = data.x_num[: len(tr)]
    model = TemporalEdgeModel(len(EDGE_NUM_NAMES), g.n_cur, g.n_fmt, x_tr.mean(0), x_tr.std(0).clamp(min=1e-3),
                              d_model=args.d_model, heads=args.heads, attn=attn).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    pos_tr = tr[g.y[tr] == 1]
    neg_tr = tr[g.y[tr] == 0]
    rng = np.random.default_rng(args.seed)
    pos_weight = torch.tensor(args.pos_weight, device=device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[{attn}] params={n_params:,} train pos={len(pos_tr):,} neg/epoch={int(len(neg_tr) * args.neg_frac):,}")

    best, history, step = {"pr_auc": -1}, [], 0
    t0 = time.time()
    for ep in range(args.epochs):
        model.train()
        ids = np.concatenate([pos_tr, rng.choice(neg_tr, int(len(neg_tr) * args.neg_frac), replace=False)])
        rng.shuffle(ids)
        losses = []
        for i in range(0, len(ids), args.batch_size):
            idx = torch.as_tensor(ids[i:i + args.batch_size], device=device)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logit = model(data.batch(model, idx)).float()
            loss = F.binary_cross_entropy_with_logits(logit, data.y[idx], pos_weight=pos_weight)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(loss.item())
            step += 1
            if args.max_steps and step >= args.max_steps:
                break
        p_va = predict(model, data, va, args.eval_batch_size)
        ap = average_precision_score(g.y[va], p_va)
        lam = getattr(model.attn, "last_lambda", None)
        history.append({"epoch": ep, "loss": round(float(np.mean(losses)), 4), "valid_pr_auc": round(ap, 4),
                        "lambda": None if lam is None else round(float(lam), 4)})
        print(f"[{attn}] epoch {ep} loss {np.mean(losses):.4f} valid PR-AUC {ap:.4f}"
              + ("" if lam is None else f" lambda {float(lam):.3f}") + f" ({time.time() - t0:.0f}s)")
        if ap > best["pr_auc"]:
            best = {"pr_auc": ap, "epoch": ep}
            CKPT_DIR.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": model.state_dict(), "args": vars(args), "attn": attn}, CKPT_DIR / f"aml_{attn}_s{args.seed}.pt")
        if args.max_steps and step >= args.max_steps:
            break

    model.load_state_dict(torch.load(CKPT_DIR / f"aml_{attn}_s{args.seed}.pt", weights_only=False)["state_dict"])
    p_va = predict(model, data, va, args.eval_batch_size)
    p_te = predict(model, data, te, args.eval_batch_size)
    np.savez(CKPT_DIR / f"aml_{attn}_s{args.seed}_preds.npz", va=p_va, te=p_te)
    thr = best_f1_threshold(g.y[va], p_va)
    return {"model": f"tgnn_{attn}", "params": n_params, "best_epoch": best["epoch"], "train_seconds": round(time.time() - t0),
            "valid": metrics(g.y[va], p_va, thr), "test": metrics(g.y[te], p_te, thr), "history": history}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--attn", nargs="+", default=["diff", "vanilla"], choices=["diff", "vanilla"])
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--k", type=int, default=32, help="neighbours per endpoint")
    ap.add_argument("--d-model", type=int, default=128)
    ap.add_argument("--heads", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch-size", type=int, default=2048)
    ap.add_argument("--eval-batch-size", type=int, default=16384)
    ap.add_argument("--neg-frac", type=float, default=0.1)
    ap.add_argument("--pos-weight", type=float, default=10.0)
    ap.add_argument("--max-steps", type=int, default=0, help="stop early (dry run)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    device = torch.device("cuda")
    t0 = time.time()
    g = load_aml()
    tr, va, te = g.splits()
    print(f"edges {g.n_edges:,} nodes {g.n_nodes:,} | positives train {g.y[tr].sum()} valid {g.y[va].sum()} "
          f"test {g.y[te].sum()} | loaded in {time.time() - t0:.0f}s")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for attn in args.attn:
        res = run(attn, g, args, device)
        res["config"] = vars(args)
        (REPORT_DIR / f"gnn_aml_{attn}_s{args.seed}.json").write_text(json.dumps(res, indent=2, default=float))
        print(f"[{attn}] TEST {res['test']}")


if __name__ == "__main__":
    main()
