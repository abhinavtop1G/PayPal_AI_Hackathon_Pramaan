"""1D-CNN keystroke encoder -> L2-normalised typing embedding.

Input is the raw 31 timings of one password attempt. The encoder lays them out as a sequence over the 11 key
positions, 4 channels each: log hold time, log down-down latency to the next key, signed-log up-down latency to the
next key, and a has-next flag (0 for the last key). Channels are standardised with constants fitted on training users
and stored as buffers, so the saved model takes raw timings directly. A 1D-CNN with dilated residual blocks reads
the rhythm across neighbouring keys; mean + max pooling gives one vector, projected and L2-normalised.

Trained as a user classifier with CosFace (shared with the touch model); at test time only the embedding is used, so
new users are enrolled without retraining.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

N_KEYS, N_CH = 11, 4


def sequence(raw: torch.Tensor) -> torch.Tensor:
    """[B, 31] seconds -> [B, 11, 4] (log H, log DD, signed-log UD, has_next)."""
    b = raw.shape[0]
    pairs = raw[:, :30].reshape(b, 10, 3)
    h = torch.cat([pairs[..., 0], raw[:, 30:31]], 1).clamp(min=1e-4)
    dd = F.pad(pairs[..., 1], (0, 1)).clamp(min=0)
    ud = F.pad(pairs[..., 2], (0, 1))
    nxt = F.pad(torch.ones_like(pairs[..., 0]), (0, 1))
    return torch.stack([torch.log(h), torch.log1p(dd * 10), torch.sign(ud) * torch.log1p(ud.abs() * 10), nxt], -1)


class ResBlock(nn.Module):
    def __init__(self, ch: int, dilation: int, dropout: float):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(ch, ch, 3, padding=dilation, dilation=dilation), nn.BatchNorm1d(ch), nn.GELU(), nn.Dropout(dropout),
            nn.Conv1d(ch, ch, 3, padding=1), nn.BatchNorm1d(ch))

    def forward(self, x):
        return F.gelu(x + self.net(x))


class KeystrokeEncoder(nn.Module):
    def __init__(self, ch: int = 64, emb: int = 64, dropout: float = 0.2, dilations=(1, 2, 1)):
        super().__init__()
        self.register_buffer("mu", torch.zeros(N_KEYS, N_CH))
        self.register_buffer("sd", torch.ones(N_KEYS, N_CH))
        self.stem = nn.Sequential(nn.Conv1d(N_CH, ch, 3, padding=1), nn.BatchNorm1d(ch), nn.GELU())
        self.blocks = nn.Sequential(*[ResBlock(ch, d, dropout) for d in dilations])
        self.proj = nn.Sequential(nn.Dropout(dropout), nn.Linear(2 * ch, emb))

    def fit_standardiser(self, raw: torch.Tensor):
        s = sequence(raw)
        self.mu.copy_(s.mean(0))
        self.sd.copy_(s.std(0).clamp(min=1e-3))
        self.mu[-1, 1:] = 0.0  # the last key has no next key: keep its padded channels at exactly 0
        self.sd[-1, 1:] = 1.0
        return self

    def forward(self, raw: torch.Tensor) -> torch.Tensor:
        """raw [B, 31] seconds -> unit embedding [B, emb]."""
        x = ((sequence(raw) - self.mu) / self.sd).clamp(-6, 6).transpose(1, 2)   # [B, 4, 11]
        h = self.blocks(self.stem(x))
        return F.normalize(self.proj(torch.cat([h.mean(-1), h.amax(-1)], -1)), dim=-1)
