"""Online scoring of account-to-account transfers with the temporal GNN.

History = the IBM AML HI-Small edge store (on device) + an in-memory buffer of transfers scored
through the API. For a new transfer u -> v the model attends over each endpoint's K most recent
interactions before it, exactly as in training. Unknown accounts are allowed (no history).
"""
import json
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from ml.models.gnn.data import EDGE_NUM_NAMES, load_aml, load_vocab
from ml.models.gnn.model import TemporalEdgeModel
from ml.models.gnn.sampler import IN, OUT, TemporalNeighborSampler

ART = Path("ml/models/gnn/artifacts")


class GNNService:
    def __init__(self, attn: str = "diff", device: str = "cuda"):
        self.device = torch.device(device)
        ck = torch.load(ART / f"aml_{attn}.pt", weights_only=False, map_location=self.device)
        self.meta = json.loads((ART / f"aml_{attn}.meta.json").read_text())
        self.threshold = float(self.meta["decision_threshold"])
        self.k = int(ck["args"]["k"])
        g = load_aml()
        v = load_vocab()
        self.accounts = v["accounts"]
        self.acct_id = {a: i for i, a in enumerate(self.accounts)}
        self.currencies, self.formats, self.t0 = v["currencies"], v["formats"], v["t0"]
        sd = ck["state_dict"]
        self.model = TemporalEdgeModel(len(EDGE_NUM_NAMES), g.n_cur, g.n_fmt, sd["edge_enc.mean"], sd["edge_enc.std"],
                                       d_model=ck["args"]["d_model"], heads=ck["args"]["heads"], attn=attn).to(self.device)
        self.model.load_state_dict(sd)
        self.model.eval()
        to = lambda a: torch.as_tensor(a, device=self.device)  # noqa: E731
        self.src, self.dst, self.t = to(g.src), to(g.dst), to(g.t)
        self.x_num, self.cur_paid, self.cur_recv, self.fmt = to(g.x_num), to(g.cur_paid), to(g.cur_recv), to(g.fmt)
        self.n_hist_nodes, self.n_edges = g.n_nodes, g.n_edges
        self.sampler = TemporalNeighborSampler(self.src, self.dst, g.n_nodes, self.k)
        self.buffer: dict[int, list] = {}   # node -> [(t, x_num, cur_paid, cur_recv, fmt, direction, counterpart)]
        self.new_accounts: list[str] = []
        self.lock = threading.Lock()
        self.attn = attn

    # ------------------------------------------------------------------ helpers
    def _node(self, bank: str, acct: str, create: bool) -> int:
        key = f"{bank}_{acct}"
        if key not in self.acct_id and create:
            self.acct_id[key] = self.n_hist_nodes + len(self.new_accounts)
            self.new_accounts.append(key)
        return self.acct_id.get(key, -1)

    def _account_name(self, node: int) -> str:
        return self.accounts[node] if node < self.n_hist_nodes else self.new_accounts[node - self.n_hist_nodes]

    def _edge_features(self, r: dict, minutes: int):
        if r["payment_currency"] not in self.currencies or r["receiving_currency"] not in self.currencies:
            raise ValueError(f"unknown currency; known: {self.currencies}")
        if r["payment_format"] not in self.formats:
            raise ValueError(f"unknown payment format; known: {self.formats}")
        ts = pd.Timestamp(r["timestamp"])
        hour = ts.hour + ts.minute / 60
        x = np.array([np.log1p(r["amount_paid"]), np.log1p(r["amount_received"]),
                      float(r["payment_currency"] != r["receiving_currency"]),
                      float(r["from_bank"] == r["to_bank"] and r["from_account"] == r["to_account"]),
                      float(r["from_bank"] == r["to_bank"]), np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)],
                     dtype="float32")
        return x, self.currencies.index(r["payment_currency"]), self.currencies.index(r["receiving_currency"]), \
            self.formats.index(r["payment_format"])

    def _neighbours(self, node: int, t_now: int, as_of_edge: int | None = None):
        """(K most recent interactions of `node` (history + API buffer), oldest -> newest; total prior count).
        `as_of_edge` restricts history to edges before that index (used to re-score historical transfers).
        The total count (not capped at K) is a model input, as in training."""
        items, total = [], 0
        if 0 <= node < self.n_hist_nodes:
            before = self.n_edges if as_of_edge is None else as_of_edge
            nb, d, m, n_prior = self.sampler.sample(torch.as_tensor([node], device=self.device),
                                                    torch.as_tensor([before], device=self.device))
            total += int(n_prior[0])
            for e, di, ok in zip(nb[0].tolist(), d[0].tolist(), m[0].tolist()):
                if ok:
                    cp = int(self.dst[e]) if di == OUT else int(self.src[e])
                    items.append((int(self.t[e]), ("hist", e), di, cp))
        for j, rec in enumerate(self.buffer.get(node, []) if as_of_edge is None else []):
            items.append((rec[0], ("buf", node, j), rec[5], rec[6]))
            total += 1
        items.sort(key=lambda x: x[0])
        return [it for it in items if it[0] <= t_now][-self.k:], total

    def _encode(self, items):
        hist = [it[1][1] for it in items if it[1][0] == "hist"]
        xs, cps, crs, fs = [], [], [], []
        hi = 0
        for it in items:
            if it[1][0] == "hist":
                e = hist[hi]; hi += 1
                xs.append(self.x_num[e]); cps.append(self.cur_paid[e]); crs.append(self.cur_recv[e]); fs.append(self.fmt[e])
            else:
                rec = self.buffer[it[1][1]][it[1][2]]
                xs.append(torch.as_tensor(rec[1], device=self.device)); cps.append(torch.as_tensor(rec[2], device=self.device))
                crs.append(torch.as_tensor(rec[3], device=self.device)); fs.append(torch.as_tensor(rec[4], device=self.device))
        return self.model.edge_enc(torch.stack(xs), torch.stack(cps), torch.stack(crs), torch.stack(fs))

    # ------------------------------------------------------------------ API
    @torch.no_grad()
    def score(self, r: dict, record: bool = True, as_of_edge: int | None = None) -> dict:
        """bf16 autocast on CUDA, as in offline evaluation, so the published threshold/metrics apply exactly."""
        t_start = time.perf_counter()
        with self.lock, torch.autocast("cuda", dtype=torch.bfloat16, enabled=self.device.type == "cuda"):
            minutes = int((pd.Timestamp(r["timestamp"]) - self.t0).total_seconds() // 60)
            x, cp, cr, f = self._edge_features(r, minutes)
            u = self._node(r["from_bank"], r["from_account"], create=True)
            v = self._node(r["to_bank"], r["to_account"], create=True)
            dev = self.device
            e_emb = self.model.edge_enc(torch.as_tensor(x, device=dev)[None], torch.as_tensor([cp], device=dev),
                                        torch.as_tensor([cr], device=dev), torch.as_tensor([f], device=dev))
            sides, explain = [], {}
            for name, node, role in (("sender", u, OUT), ("receiver", v, IN)):
                items, total = self._neighbours(node, minutes, as_of_edge)
                k = self.k
                nb_emb = torch.zeros(1, k, e_emb.shape[1], device=dev)
                dt = torch.zeros(1, k, dtype=torch.long, device=dev)
                dirs = torch.zeros(1, k, dtype=torch.long, device=dev)
                mask = torch.zeros(1, k, dtype=torch.bool, device=dev)
                if items:
                    n = len(items)
                    nb_emb[0, k - n:] = self._encode(items)
                    dt[0, k - n:] = torch.as_tensor([minutes - it[0] for it in items], device=dev)
                    dirs[0, k - n:] = torch.as_tensor([it[2] for it in items], device=dev)
                    mask[0, k - n:] = True
                n_prior = torch.as_tensor([total], device=dev)
                h, attn = self.model.node_embed(e_emb, torch.as_tensor([role], device=dev), nb_emb, dt, dirs, mask,
                                                n_prior, return_attn=True)
                sides.append(h)
                w = attn[0].float().mean(0)[k - len(items):].cpu().numpy() if items else np.array([])
                top = np.argsort(np.abs(w))[::-1][:3]
                explain[name] = {
                    "account": self._account_name(node), "history_used": len(items), "history_total": total,
                    "top_attended": [{"counterparty": self._account_name(items[i][3]),
                                      "direction": "out" if items[i][2] == OUT else "in",
                                      "minutes_before": int(minutes - items[i][0]), "weight": round(float(w[i]), 4)}
                                     for i in top]}
            p = float(torch.sigmoid(self.model.head(torch.cat([sides[0], sides[1], e_emb], -1)).float()).squeeze())
            if record:
                for node, direction, other in ((u, OUT, v), (v, IN, u)):
                    self.buffer.setdefault(node, []).append((minutes, x, cp, cr, f, direction, other))
        return {"p_laundering": round(p, 5), "flagged": p >= self.threshold, "threshold": self.threshold,
                "model": f"temporal GNN ({self.attn} attention)", "explanation": explain,
                "latency_ms": round(1000 * (time.perf_counter() - t_start), 2)}

    def reset(self) -> None:
        with self.lock:
            self.buffer.clear()
            for a in self.new_accounts:
                self.acct_id.pop(a, None)
            self.new_accounts.clear()
