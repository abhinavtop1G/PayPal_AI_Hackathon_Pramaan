"""Train the 1D-CNN keystroke encoder on CMU DSL-StrongPassword and track open-set EER on valid users.

    python -m ml.models.keystroke.train --seed 0
    python -m ml.models.keystroke.train --epochs 1 --max-steps 30      # dry run

Users are split once (--split-seed, same 70/15/15 split helper as the touch model) into train / valid / test;
--seed only changes initialisation. Augmentations act on the raw timings, as real typing varies: a global speed
factor (the whole attempt typed faster or slower), per-key jitter, and occasionally one key's timings replaced by
the user's typical value.
Checkpoint: checkpoints/keystroke/cnn_s<seed>.pt; result: ml/reports/keystroke_cnn_s<seed>.json.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from ml.models.biometrics.model import CosFaceHead
from ml.models.biometrics.windows import split_users

from .data import ENROL_SESSIONS, load_cmu, timings
from .model import KeystrokeEncoder
from .protocol import score, sims

CKPT_DIR = Path("checkpoints/keystroke")
REPORT_DIR = Path("ml/reports")


@torch.no_grad()
def embed(model, raw: np.ndarray, device, bs: int = 8192) -> np.ndarray:
    model.eval()
    return torch.cat([model(torch.as_tensor(raw[i:i + bs], device=device)).cpu() for i in range(0, len(raw), bs)]).numpy()


def open_set(model, df, raw, users, device) -> dict:
    m = df["user"].isin(users).to_numpy()
    emb = embed(model, raw[m], device)
    user, sess = df["user"].to_numpy()[m], df["session"].to_numpy()[m]
    enrol, probe = np.isin(sess, list(ENROL_SESSIONS)), ~np.isin(sess, list(ENROL_SESSIONS))
    us = np.array(sorted(users))
    s = sims("cnn", us, enrol, probe, user, emb=emb)
    return score(s, np.searchsorted(us, user[probe]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--ch", type=int, default=64)
    ap.add_argument("--emb", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--speed", type=float, default=0.12, help="std of the log global-speed factor")
    ap.add_argument("--jitter", type=float, default=0.08, help="std of log per-timing jitter")
    ap.add_argument("--margin", type=float, default=0.25)
    ap.add_argument("--patience", type=int, default=25)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--split-seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--tag", default="", help="suffix for checkpoint/report names (sweeps)")
    a = ap.parse_args(argv)
    torch.manual_seed(a.seed)
    rng = np.random.default_rng(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    df = load_cmu()
    raw = timings(df)
    tr, va, te = split_users(df["user"].unique(), a.split_seed)
    trm = df["user"].isin(tr).to_numpy()
    ids = {u: i for i, u in enumerate(sorted(tr))}
    x_tr = torch.as_tensor(raw[trm], device=device)
    y_tr = torch.as_tensor(df.loc[trm, "user"].map(ids).to_numpy(), device=device)

    model = KeystrokeEncoder(a.ch, a.emb, a.dropout).to(device).fit_standardiser(x_tr)
    head = CosFaceHead(a.emb, len(tr), scale=16.0, margin=a.margin).to(device)
    opt = torch.optim.AdamW(list(model.parameters()) + list(head.parameters()), lr=a.lr, weight_decay=a.weight_decay)
    steps_per_epoch = int(np.ceil(len(x_tr) / a.batch_size))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * steps_per_epoch)
    typical = x_tr.median(0).values

    best, best_state, bad, step, log = 1.0, None, 0, 0, []
    t0 = time.time()
    for ep in range(a.epochs):
        model.train()
        head.train()
        perm = torch.as_tensor(rng.permutation(len(x_tr)), device=device)
        tot = 0.0
        for i in range(0, len(perm), a.batch_size):
            b = perm[i:i + a.batch_size]
            x = x_tr[b]
            x = x * torch.exp(torch.randn(len(x), 1, device=device) * a.speed)           # whole attempt faster/slower
            x = x * torch.exp(torch.randn_like(x) * a.jitter)                            # per-timing jitter
            drop = torch.rand_like(x) < 0.03                                             # an odd hesitation smoothed out
            x = torch.where(drop, typical.expand_as(x), x)
            loss = F.cross_entropy(head(model(x), y_tr[b]), y_tr[b])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(b)
            step += 1
            if a.max_steps and step >= a.max_steps:
                break
        v = open_set(model, df, raw, va, device)
        log.append({"epoch": ep, "loss": round(tot / len(x_tr), 4), "valid_eer": v["eer"], "valid_per_user": v["per_user_eer_mean"]})
        if v["per_user_eer_mean"] < best:
            best, bad = v["per_user_eer_mean"], 0
            best_state = {k: t.detach().cpu().clone() for k, t in model.state_dict().items()}
        else:
            bad += 1
        if ep % 10 == 0 or bad == 0:
            print(f"ep {ep:3d} loss {log[-1]['loss']:.3f} valid EER {v['eer']:.4f} per-user {v['per_user_eer_mean']:.4f}"
                  f"{'  *' if bad == 0 else ''}", flush=True)
        if (a.max_steps and step >= a.max_steps) or bad >= a.patience:
            break

    model.load_state_dict(best_state)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt = CKPT_DIR / f"cnn{a.tag}_s{a.seed}.pt"
    torch.save({"state_dict": best_state, "args": vars(a), "split": {"train": sorted(map(int, tr)), "valid": sorted(map(int, va)),
                                                                     "test": sorted(map(int, te))}}, ckpt)
    res = {"seed": a.seed, "best_valid_per_user_eer": best, "valid": open_set(model, df, raw, va, device),
           "epochs_run": len(log), "seconds": round(time.time() - t0, 1), "params": sum(p.numel() for p in model.parameters()),
           "checkpoint": str(ckpt), "log": log}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"keystroke_cnn{a.tag}_s{a.seed}.json").write_text(json.dumps(res, indent=2))
    print(f"best valid per-user EER {best:.4f} after {len(log)} epochs ({res['seconds']} s) -> {ckpt}")
    return res


if __name__ == "__main__":
    main()
