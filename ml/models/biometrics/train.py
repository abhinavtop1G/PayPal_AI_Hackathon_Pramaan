"""Train the HMOG gesture-sequence LSTM and evaluate open-set verification EER.

    python -m ml.models.biometrics.train --seed 0
    python -m ml.models.biometrics.train --epochs 1 --max-steps 30     # dry run

Users are split once (--split-seed) into train/valid/test; --seed only changes initialisation.
Each training batch is cropped to a random length in [--min-len, 20] so the encoder works on the
short gesture bursts of a real payment flow. Reported at N = 10 and N = 20 gestures.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .data import FEATURES, load_gestures
from .metrics import verify
from .model import CosFaceHead, GestureEncoder
from .windows import make_windows, prepare

CKPT_DIR = Path("checkpoints/biometrics")
REPORT_DIR = Path("ml/reports")
EVAL_LENGTHS = (10, 20)


@torch.no_grad()
def embed(model, x: np.ndarray, device, bs: int = 4096) -> np.ndarray:
    model.eval()
    return torch.cat([model(torch.as_tensor(x[i:i + bs], device=device)).cpu()
                      for i in range(0, len(x), bs)]).numpy()


def evaluate(model, wins: dict, device) -> dict:
    return {f"n{n}": verify(embed(model, w.x, device), w.user, w.session, w.scenario) for n, w in wins.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--emb", type=int, default=128)
    ap.add_argument("--dropout", type=float, default=0.4)
    ap.add_argument("--weight-decay", type=float, default=0.05)
    ap.add_argument("--noise", type=float, default=0.3, help="Gaussian noise std on standardised inputs (train only)")
    ap.add_argument("--feat-drop", type=float, default=0.2, help="prob. of zeroing a feature for a whole window")
    ap.add_argument("--tag", default="", help="suffix for checkpoint/report names (sweeps)")
    ap.add_argument("--no-test", action="store_true", help="sweep mode: report valid only")
    ap.add_argument("--min-len", type=int, default=8)
    ap.add_argument("--train-len", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--split-seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=0)
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = torch.device("cuda")

    t0 = time.time()
    df = load_gestures()
    split, std, z = prepare(df, args.split_seed)
    part = {k: df["user"].isin(v).to_numpy() for k, v in split.items()}
    train = make_windows(df[part["train"]], z[part["train"]], args.train_len, stride=5)
    users = np.unique(train.user)
    y_train = np.searchsorted(users, train.user)
    evals = {s: {n: make_windows(df[part[s]], z[part[s]], n, stride=n) for n in EVAL_LENGTHS} for s in ("valid", "test")}
    print(f"users train/valid/test {len(split['train'])}/{len(split['valid'])}/{len(split['test'])} | "
          f"train windows {len(train.x):,} | valid N20 {len(evals['valid'][20].x):,} | prep {time.time() - t0:.0f}s")

    model = GestureEncoder(len(FEATURES), args.hidden, emb=args.emb, dropout=args.dropout).to(device)
    head = CosFaceHead(args.emb, len(users)).to(device)
    opt = torch.optim.AdamW(list(model.parameters()) + list(head.parameters()), lr=args.lr,
                            weight_decay=args.weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    X = torch.as_tensor(train.x, device=device)
    Y = torch.as_tensor(y_train, device=device)

    best, history, step = {"score": 1e9}, [], 0
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"hmog_lstm{args.tag}_s{args.seed}"
    ckpt = CKPT_DIR / f"{name}.pt"
    for ep in range(args.epochs):
        model.train()
        head.train()
        perm = torch.as_tensor(rng.permutation(len(X)), device=device)
        losses, correct = [], 0
        for i in range(0, len(perm), args.batch_size):
            idx = perm[i:i + args.batch_size]
            L = int(rng.integers(args.min_len, args.train_len + 1))
            off = int(rng.integers(0, args.train_len - L + 1))
            xb = X[idx, off:off + L]
            if args.noise:
                xb = xb + args.noise * torch.randn_like(xb)
            if args.feat_drop:
                keep = (torch.rand(xb.shape[0], 1, xb.shape[2], device=device) > args.feat_drop).float()
                xb = xb * keep
            e = model(xb)
            logits = head(e, Y[idx])
            loss = F.cross_entropy(logits, Y[idx])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            losses.append(loss.item())
            correct += (logits.argmax(1) == Y[idx]).sum().item()
            step += 1
            if args.max_steps and step >= args.max_steps:
                break
        sched.step()
        val = evaluate(model, evals["valid"], device)
        score = np.mean([val[f"n{n}"]["eer"] for n in EVAL_LENGTHS])
        history.append({"epoch": ep, "loss": round(float(np.mean(losses)), 4),
                        "train_acc": round(correct / len(perm), 4), **{f"valid_eer_n{n}": val[f"n{n}"]["eer"] for n in EVAL_LENGTHS}})
        print(f"epoch {ep:2d} loss {np.mean(losses):.3f} train-acc {correct / len(perm):.3f} "
              f"valid EER N10 {val['n10']['eer']:.4f} N20 {val['n20']['eer']:.4f} ({time.time() - t0:.0f}s)")
        if score < best["score"]:
            best = {"score": score, "epoch": ep}
            torch.save({"state_dict": model.state_dict(), "args": vars(args), "features": FEATURES,
                        "std_mean": std.mean, "std_std": std.std, "split": {k: sorted(map(int, v)) for k, v in split.items()}},
                       ckpt)
        if args.max_steps and step >= args.max_steps:
            break

    model.load_state_dict(torch.load(ckpt, weights_only=False)["state_dict"])
    res = {"model": "bilstm_cosface", "seed": args.seed, "best_epoch": best["epoch"],
           "params": sum(p.numel() for p in model.parameters()),
           "valid": evaluate(model, evals["valid"], device),
           "history": history, "config": vars(args)}
    if args.no_test:
        print("VALID", json.dumps({k: v["eer"] for k, v in res["valid"].items()}), "best_epoch", best["epoch"])
        return
    res["test"] = evaluate(model, evals["test"], device)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"biometrics_{name}.json").write_text(json.dumps(res, indent=2, default=float))
    print("TEST", json.dumps(res["test"]))


if __name__ == "__main__":
    main()
