"""Temporal edge classifier with Differential Attention over each endpoint's recent interactions.

For transaction e = (u -> v, t):
  h_u = Attn(query = [edge e, "out"], keys = u's last K events before e)
  h_v = Attn(query = [edge e, "in"],  keys = v's last K events before e)
  p(laundering) = MLP([h_u, h_v, enc(e)])

Neighbour event j is encoded from its edge features, its direction relative to the node, and a
learned encoding of the time gap t - t_j.

Differential attention (Ye et al., "Differential Transformer", 2024):
  A = softmax(Q1 K1^T / sqrt(d)) - lambda * softmax(Q2 K2^T / sqrt(d))
  lambda = exp(lq1 . lk1) - exp(lq2 . lk2) + lambda_init
The second map learns the "common-mode" attention (routine counterparties, salary/merchant noise)
and subtracts it, so the head can concentrate on the few anomalous interactions.
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class TimeEncoder(nn.Module):
    """phi(dt) = cos(w * log1p(dt) + b), learnable frequencies (TGAT-style, log-scaled gaps)."""

    def __init__(self, dim: int):
        super().__init__()
        self.lin = nn.Linear(1, dim)
        with torch.no_grad():
            self.lin.weight.copy_(torch.logspace(0, -3, dim).unsqueeze(1) * 10)
            self.lin.bias.zero_()

    def forward(self, dt: torch.Tensor) -> torch.Tensor:
        return torch.cos(self.lin(torch.log1p(dt.clamp(min=0).float()).unsqueeze(-1)))


class EdgeEncoder(nn.Module):
    def __init__(self, n_num: int, n_cur: int, n_fmt: int, dim: int, num_mean: torch.Tensor, num_std: torch.Tensor):
        super().__init__()
        self.register_buffer("mean", num_mean)
        self.register_buffer("std", num_std)
        self.cur = nn.Embedding(n_cur, 8)
        self.fmt = nn.Embedding(n_fmt, 8)
        self.proj = nn.Sequential(nn.Linear(n_num + 24, dim), nn.GELU(), nn.Linear(dim, dim))

    def forward(self, x_num, cur_paid, cur_recv, fmt):
        x = (x_num - self.mean) / self.std
        return self.proj(torch.cat([x, self.cur(cur_paid), self.cur(cur_recv), self.fmt(fmt)], -1))


def _masked_softmax(scores: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """scores [B,H,K], mask [B,K]; rows with no valid key give all-zero weights instead of NaN."""
    scores = scores.masked_fill(~mask[:, None, :], float("-inf"))
    w = torch.softmax(scores, dim=-1)
    return torch.nan_to_num(w, nan=0.0)


class DiffAttention(nn.Module):
    def __init__(self, d_q: int, d_kv: int, d_model: int, heads: int, layer_idx: int = 1):
        super().__init__()
        assert d_model % (2 * heads) == 0
        self.h, self.dh = heads, d_model // heads // 2  # each head: two query/key halves of size dh
        self.q = nn.Linear(d_q, d_model, bias=False)
        self.k = nn.Linear(d_kv, d_model, bias=False)
        self.v = nn.Linear(d_kv, d_model, bias=False)  # value per head has size 2*dh
        self.out = nn.Linear(d_model, d_model)
        self.lambda_init = 0.8 - 0.6 * math.exp(-0.3 * (layer_idx - 1))
        self.lq1, self.lk1, self.lq2, self.lk2 = (nn.Parameter(torch.randn(self.dh) * 0.1) for _ in range(4))
        self.norm = nn.GroupNorm(heads, d_model)  # per-head normalisation of the differential output
        self.last_lambda = None

    def lam(self) -> torch.Tensor:
        return (torch.exp(self.lq1 @ self.lk1) - torch.exp(self.lq2 @ self.lk2) + self.lambda_init)

    def forward(self, q_in, kv, mask, return_attn: bool = False):
        b, k, _ = kv.shape
        q = self.q(q_in).view(b, self.h, 2, self.dh)
        key = self.k(kv).view(b, k, self.h, 2, self.dh)
        v = self.v(kv).view(b, k, self.h, 2 * self.dh)
        scale = self.dh ** -0.5
        a1 = _masked_softmax(torch.einsum("bhd,bkhd->bhk", q[:, :, 0], key[..., 0, :]) * scale, mask)
        a2 = _masked_softmax(torch.einsum("bhd,bkhd->bhk", q[:, :, 1], key[..., 1, :]) * scale, mask)
        lam = self.lam()
        self.last_lambda = lam.detach()  # tensor; converting to float here would force a GPU sync every step
        attn = a1 - lam * a2
        o = torch.einsum("bhk,bkhd->bhd", attn, v).reshape(b, -1)
        o = self.norm(o) * (1 - self.lambda_init)
        o = self.out(o)
        return (o, attn) if return_attn else o


class VanillaAttention(nn.Module):
    """Same parameter budget as DiffAttention, single softmax map."""

    def __init__(self, d_q: int, d_kv: int, d_model: int, heads: int, layer_idx: int = 1):
        super().__init__()
        self.h, self.dh = heads, d_model // heads
        self.q = nn.Linear(d_q, d_model, bias=False)
        self.k = nn.Linear(d_kv, d_model, bias=False)
        self.v = nn.Linear(d_kv, d_model, bias=False)
        self.out = nn.Linear(d_model, d_model)
        self.norm = nn.GroupNorm(heads, d_model)

    def forward(self, q_in, kv, mask, return_attn: bool = False):
        b, k, _ = kv.shape
        q = self.q(q_in).view(b, self.h, self.dh)
        key = self.k(kv).view(b, k, self.h, self.dh)
        v = self.v(kv).view(b, k, self.h, self.dh)
        attn = _masked_softmax(torch.einsum("bhd,bkhd->bhk", q, key) * self.dh ** -0.5, mask)
        o = self.out(self.norm(torch.einsum("bhk,bkhd->bhd", attn, v).reshape(b, -1)))
        return (o, attn) if return_attn else o


ATTENTION = {"diff": DiffAttention, "vanilla": VanillaAttention}


class TemporalEdgeModel(nn.Module):
    def __init__(self, n_num, n_cur, n_fmt, num_mean, num_std, d_edge=64, d_time=32, d_model=128, heads=4,
                 attn="diff"):
        super().__init__()
        self.edge_enc = EdgeEncoder(n_num, n_cur, n_fmt, d_edge, num_mean, num_std)
        self.time_enc = TimeEncoder(d_time)
        self.dir_emb = nn.Embedding(2, 8)
        d_kv = d_edge + d_time + 8
        d_q = d_edge + 8 + 1  # current edge, role of the node in it, log #prior events
        self.attn = ATTENTION[attn](d_q, d_kv, d_model, heads)
        self.q_skip = nn.Linear(d_q, d_model)
        self.node_ffn = nn.Sequential(nn.LayerNorm(d_model), nn.Linear(d_model, d_model), nn.GELU())
        self.head = nn.Sequential(nn.Linear(2 * d_model + d_edge, 128), nn.GELU(), nn.Dropout(0.1), nn.Linear(128, 1))

    def node_embed(self, e_cur, role, nb_edge_emb, nb_dt, nb_dir, mask, n_prior, return_attn=False):
        q = torch.cat([e_cur, self.dir_emb(role), torch.log1p(n_prior.float()).unsqueeze(-1)], -1)
        kv = torch.cat([nb_edge_emb, self.time_enc(nb_dt), self.dir_emb(nb_dir)], -1)
        out = self.attn(q, kv, mask, return_attn=return_attn)
        h, attn = out if return_attn else (out, None)
        h = self.node_ffn(h + self.q_skip(q))
        return (h, attn) if return_attn else h

    def forward(self, batch: dict, return_attn: bool = False):
        e = batch["edge_emb"]
        hu = self.node_embed(e, batch["role_u"], batch["nb_emb_u"], batch["dt_u"], batch["dir_u"], batch["mask_u"],
                             batch["n_u"], return_attn)
        hv = self.node_embed(e, batch["role_v"], batch["nb_emb_v"], batch["dt_v"], batch["dir_v"], batch["mask_v"],
                             batch["n_v"], return_attn)
        if return_attn:
            (hu, au), (hv, av) = hu, hv
            return self.head(torch.cat([hu, hv, e], -1)).squeeze(-1), au, av
        return self.head(torch.cat([hu, hv, e], -1)).squeeze(-1)
