"""BiLSTM gesture-sequence encoder -> L2-normalised behavioural embedding.

Trained as a user classifier with a cosine-margin softmax (CosFace) over training users; at test
time only the embedding is used, so unseen users can be enrolled without retraining.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class GestureEncoder(nn.Module):
    def __init__(self, n_feat: int, hidden: int = 128, layers: int = 2, emb: int = 128, dropout: float = 0.2):
        super().__init__()
        self.inp = nn.Sequential(nn.Linear(n_feat, hidden), nn.LayerNorm(hidden), nn.GELU())
        # Single-layer LSTMs with explicit dropout between them (same maths as nn.LSTM(dropout=p)).
        # cuDNN's built-in inter-layer dropout makes the process fail-fast (0xC0000409) at exit on
        # Windows with torch 2.14 / cuDNN 9.10.
        self.lstms = nn.ModuleList(
            nn.LSTM(hidden if i == 0 else 2 * hidden, hidden, batch_first=True, bidirectional=True) for i in range(layers)
        )
        self.drop = nn.Dropout(dropout)
        self.proj = nn.Sequential(nn.Dropout(dropout), nn.Linear(4 * hidden, emb))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x [B, N, F] -> unit embedding [B, emb]; works for any window length N."""
        h = self.inp(x)
        for i, lstm in enumerate(self.lstms):
            h, _ = lstm(self.drop(h) if i > 0 else h)
        pooled = torch.cat([h.mean(1), h.max(1).values], -1)
        return F.normalize(self.proj(pooled), dim=-1)


class CosFaceHead(nn.Module):
    def __init__(self, emb: int, n_classes: int, scale: float = 16.0, margin: float = 0.2):
        super().__init__()
        self.w = nn.Parameter(torch.randn(n_classes, emb) * 0.01)
        self.s, self.m = scale, margin

    def forward(self, e: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        cos = e @ F.normalize(self.w, dim=-1).T
        return self.s * (cos - self.m * F.one_hot(y, cos.shape[1]))
