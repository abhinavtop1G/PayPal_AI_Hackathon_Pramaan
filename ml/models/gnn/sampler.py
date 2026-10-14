"""Vectorised temporal neighbour sampler (GPU-friendly, no torch-geometric).

Every edge e = (u -> v) creates two events: an "out" event on u and an "in" event on v. Events are
stored in one array sorted by (node, edge index). For a query (node n, edge e) the K most recent
events of n with edge index < e are a contiguous slice found with a single searchsorted, so a
query can never see the edge it is scoring or anything after it.
"""
import torch

OUT, IN = 0, 1


class TemporalNeighborSampler:
    def __init__(self, src: torch.Tensor, dst: torch.Tensor, n_nodes: int, k: int):
        e = len(src)
        dev = src.device
        self.n_edges, self.k = e, k
        edge = torch.arange(e, device=dev)
        node = torch.cat([src, dst])
        direction = torch.cat([torch.full((e,), OUT, device=dev), torch.full((e,), IN, device=dev)])
        # direction is part of the key so a self-loop's OUT/IN events have a deterministic order
        key = (node * e + torch.cat([edge, edge])) * 2 + direction
        order = torch.argsort(key)
        self.key = key[order]
        self.ev_edge = torch.cat([edge, edge])[order]
        self.ev_dir = direction[order]
        self.ptr = torch.searchsorted(self.key, torch.arange(n_nodes, device=dev) * e * 2)  # first event of each node
        self._offs = torch.arange(-k, 0, device=dev)

    def sample(self, nodes: torch.Tensor, before_edge: torch.Tensor):
        """Returns (edge_ids [B,K], directions [B,K], mask [B,K], n_prior [B]); slots ordered oldest -> newest."""
        p = torch.searchsorted(self.key, (nodes * self.n_edges + before_edge) * 2)  # events with edge < before_edge
        start = self.ptr[nodes]
        idx = p[:, None] + self._offs[None, :]
        mask = idx >= start[:, None]
        idx = idx.clamp(min=0)
        return self.ev_edge[idx], self.ev_dir[idx], mask, p - start
