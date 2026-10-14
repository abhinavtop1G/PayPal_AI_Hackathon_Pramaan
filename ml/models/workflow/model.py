"""Causal GRU over a session's event stream with three heads, all emitted at every event:
  scam    - P(a scam is in progress), used for alerting at payment attempts
  stage   - current workflow stage (none / contact / pretext / isolation / extraction)
  typology- which workflow this session looks like (4 scams + benign look-alikes)

The GRU is unidirectional, so the output at event t depends only on events <= t.
"""
import torch
import torch.nn as nn

from .data import CAT_COLS, STAGES, TYPOLOGIES

CAT_DIMS = {"event": 16, "caller_kind": 4, "sms_sender_kind": 3, "app_source": 3}


class WorkflowGRU(nn.Module):
    def __init__(self, n_num: int, num_mean: torch.Tensor, num_std: torch.Tensor, d: int = 128, layers: int = 2,
                 dropout: float = 0.2):
        super().__init__()
        self.register_buffer("mean", num_mean)
        self.register_buffer("std", num_std)
        self.embs = nn.ModuleList(nn.Embedding(len(v), CAT_DIMS[k]) for k, v in CAT_COLS.items())
        self.inp = nn.Sequential(nn.Linear(n_num + sum(CAT_DIMS.values()), d), nn.LayerNorm(d), nn.GELU())
        # stacked single-layer GRUs with explicit dropout (cuDNN RNN dropout crashes at exit on this Windows setup)
        self.grus = nn.ModuleList(nn.GRU(d, d, batch_first=True) for _ in range(layers))
        self.drop = nn.Dropout(dropout)
        self.scam = nn.Linear(d, 1)
        self.stage = nn.Linear(d, len(STAGES))
        self.typology = nn.Linear(d, len(TYPOLOGIES))

    def forward(self, num: torch.Tensor, cat: torch.Tensor):
        """num [B, T, F], cat [B, T, 4] -> (scam logit [B, T], stage logits [B, T, 5], typology logits [B, T, C])."""
        x = torch.cat([(num - self.mean) / self.std] + [e(cat[..., j]) for j, e in enumerate(self.embs)], -1)
        h = self.inp(x)
        for i, gru in enumerate(self.grus):
            h, _ = gru(self.drop(h) if i > 0 else h)
        return self.scam(h).squeeze(-1), self.stage(h), self.typology(h)
