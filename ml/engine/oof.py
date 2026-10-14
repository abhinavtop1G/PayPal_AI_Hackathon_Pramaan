"""Out-of-fold GRU scores for the training period, so the fusion model can be fitted on ~4x more
honest (unseen-by-the-GRU) rows than the valid split alone provides — including enough hard
negatives (legitimate sessions the GRU finds scam-like) to learn when payee intel should overrule it.

    python -m ml.engine.oof          # writes checkpoints/engine/oof_train_components.parquet

The deployed GRU is still models/workflow/artifacts/workflow_gru.pt; the K fold models are only used
to generate fusion training data (standard stacking).
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from ml.models.workflow.data import STAGES, load
from ml.models.workflow.model import WorkflowGRU
from ml.models.workflow.train import pad_batch

from .components import component_table, default_device, gru_outputs, subset

OUT = Path("checkpoints/engine/oof_train_components.parquet")
NONE = STAGES.index("none")


def train_gru(d, device, epochs=12, bs=256, seed=0):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    allnum = np.concatenate(d.num)
    m = WorkflowGRU(allnum.shape[1], torch.as_tensor(allnum.mean(0)), torch.as_tensor(allnum.std(0).clip(min=1e-3))).to(device)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    for _ in range(epochs):
        m.train()
        perm = rng.permutation(len(d.num))
        for s in range(0, len(perm), bs):
            num, cat, stage, typ, mask = pad_batch(d, perm[s:s + bs], device)
            a, b, c = m(num, cat)
            loss = (F.binary_cross_entropy_with_logits(a[mask], (stage[mask] != NONE).float())
                    + F.cross_entropy(b[mask], stage[mask]) + 0.5 * F.cross_entropy(c[mask], typ[mask]))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
            opt.step()
        sched.step()
    return m.eval()


def main(k: int = 5, device: str | None = None):
    device = device or default_device()
    t0 = time.time()
    tr = load()["train"]
    folds = np.random.default_rng(0).integers(0, k, len(tr.num))
    parts = []
    for f in range(k):
        fit, hold = np.flatnonzero(folds != f), np.flatnonzero(folds == f)
        m = train_gru(subset(tr, fit), device, seed=f)
        dh = subset(tr, hold)
        tab = component_table(dh, gru_outputs(m, dh, device))
        tab["session_idx"] = hold[tab["session_idx"].to_numpy()]  # back to train-split indices
        parts.append(tab.assign(fold=f))
        print(f"fold {f}: {len(hold):,} sessions scored ({time.time() - t0:.0f}s)")
    out = pd.concat(parts, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    hard = (~out["is_scam"]) & (out["gru_p"] > 0.2)
    print(f"{len(out):,} OOF payment attempts, {int(hard.sum())} hard negatives (benign, GRU p > 0.2) -> {OUT}")


if __name__ == "__main__":
    main()
