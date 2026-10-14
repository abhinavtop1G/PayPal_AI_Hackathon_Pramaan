"""Train the workflow GRU on simulator sessions and evaluate with the decision-time protocol.

    python -m ml.models.workflow.train --seed 0
    python -m ml.models.workflow.train --epochs 1 --max-steps 20     # dry run

Loss = BCE(scam in progress) + CE(stage) + 0.5 * CE(typology), averaged over real (unpadded) events.
Model selection on valid stage macro-F1 (the GRU's job in the pipeline is live stage tracking).
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import f1_score

from .data import STAGES, SeqData, load
from .metrics import evaluate
from .model import WorkflowGRU

CKPT_DIR = Path("checkpoints/workflow")
REPORT_DIR = Path("ml/reports")
NONE = STAGES.index("none")


def pad_batch(d: SeqData, idx: np.ndarray, device):
    T = max(len(d.num[i]) for i in idx)
    F_ = d.num[0].shape[1]
    num = np.zeros((len(idx), T, F_), "float32")
    cat = np.zeros((len(idx), T, 4), "int64")
    stage = np.zeros((len(idx), T), "int64")
    typ = np.zeros((len(idx), T), "int64")
    mask = np.zeros((len(idx), T), bool)
    for r, i in enumerate(idx):
        n = len(d.num[i])
        num[r, :n], cat[r, :n], stage[r, :n], mask[r, :n] = d.num[i], d.cat[i], d.stage[i], True
        typ[r, :n] = d.sessions["typology_id"].iloc[i]
    to = lambda a: torch.as_tensor(a, device=device)  # noqa: E731
    return to(num), to(cat), to(stage), to(typ), to(mask)


@torch.no_grad()
def predict(model, d: SeqData, device, bs: int = 1024):
    model.eval()
    scam, stage, typ = [], [], []
    for s in range(0, len(d.num), bs):
        idx = np.arange(s, min(s + bs, len(d.num)))
        num, cat, _, _, mask = pad_batch(d, idx, device)
        a, b, c = model(num, cat)
        a, b, c = torch.sigmoid(a).cpu().numpy(), b.argmax(-1).cpu().numpy(), c.argmax(-1).cpu().numpy()
        for r, i in enumerate(idx):
            n = len(d.num[i])
            scam.append(a[r, :n]); stage.append(b[r, :n]); typ.append(c[r, :n])
    return scam, stage, typ


def stage_f1(d: SeqData, stage_pred) -> float:
    scam = d.sessions["is_scam"].to_numpy()
    y = np.concatenate([s for s, k in zip(d.stage, scam) if k])
    p = np.concatenate([s for s, k in zip(stage_pred, scam) if k])
    return float(f1_score(y, p, average="macro"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=0)
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    t0 = time.time()
    data = load()
    tr = data["train"]
    allnum = np.concatenate(tr.num)
    model = WorkflowGRU(allnum.shape[1], torch.as_tensor(allnum.mean(0)), torch.as_tensor(allnum.std(0).clip(min=1e-3)),
                        d=args.d, dropout=args.dropout).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    print(f"sessions train/valid/test {len(tr.num):,}/{len(data['valid'].num):,}/{len(data['test'].num):,} | "
          f"params {sum(p.numel() for p in model.parameters()):,} | load {time.time() - t0:.0f}s")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt = CKPT_DIR / f"workflow_gru_s{args.seed}.pt"
    best, history, step = -1.0, [], 0
    for ep in range(args.epochs):
        model.train()
        losses = []
        perm = rng.permutation(len(tr.num))
        for s in range(0, len(perm), args.batch_size):
            num, cat, stage, typ, mask = pad_batch(tr, perm[s:s + args.batch_size], device)
            a, b, c = model(num, cat)
            m = mask
            loss = (F.binary_cross_entropy_with_logits(a[m], (stage[m] != NONE).float())
                    + F.cross_entropy(b[m], stage[m]) + 0.5 * F.cross_entropy(c[m], typ[m]))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(loss.item())
            step += 1
            if args.max_steps and step >= args.max_steps:
                break
        sched.step()
        _, st_va, _ = predict(model, data["valid"], device)
        f1 = stage_f1(data["valid"], st_va)
        history.append({"epoch": ep, "loss": round(float(np.mean(losses)), 4), "valid_stage_macro_f1": round(f1, 4)})
        print(f"epoch {ep:2d} loss {np.mean(losses):.4f} valid stage macro-F1 {f1:.4f} ({time.time() - t0:.0f}s)")
        if f1 > best:
            best = f1
            torch.save({"state_dict": model.state_dict(), "args": vars(args), "num_names": tr.num_names}, ckpt)
        if args.max_steps and step >= args.max_steps:
            break

    model.load_state_dict(torch.load(ckpt, weights_only=False)["state_dict"])
    sc_va, _, _ = predict(model, data["valid"], device)
    sc_te, st_te, ty_te = predict(model, data["test"], device)
    res = {"model": "workflow_gru", "seed": args.seed, "best_valid_stage_macro_f1": round(best, 4),
           **evaluate(sc_va, data["valid"], sc_te, data["test"], st_te, ty_te), "history": history, "config": vars(args)}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"workflow_gru_s{args.seed}.json").write_text(json.dumps(res, indent=2, default=float))
    print("TEST", json.dumps({k: res[k] for k in ("payment_attempt_pr_auc", "stage_macro_f1_scam_sessions",
                                                  "stage_accuracy_scam_sessions", "typology_acc_at_first_extraction")}))


if __name__ == "__main__":
    main()
