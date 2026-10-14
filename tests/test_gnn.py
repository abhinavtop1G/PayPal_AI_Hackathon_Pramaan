import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ml.models.gnn.model import DiffAttention, TemporalEdgeModel, VanillaAttention  # noqa: E402
from ml.models.gnn.sampler import IN, OUT, TemporalNeighborSampler  # noqa: E402


def _toy_graph(e=500, n=40, seed=0):
    rng = np.random.default_rng(seed)
    return torch.as_tensor(rng.integers(0, n, e)), torch.as_tensor(rng.integers(0, n, e)), n


def test_sampler_matches_bruteforce_and_is_causal():
    src, dst, n = _toy_graph()
    src[::7] = dst[::7]  # plenty of self-loops (11.6% of AML edges)
    k = 5
    s = TemporalNeighborSampler(src, dst, n, k)
    rng = np.random.default_rng(1)
    nodes = torch.as_tensor(rng.integers(0, n, 200))
    before = torch.as_tensor(rng.integers(0, len(src), 200))
    edges, dirs, mask, n_prior = s.sample(nodes, before)
    S, D = src.numpy(), dst.numpy()
    for i in range(200):
        node, b = int(nodes[i]), int(before[i])
        events = [(e, OUT) for e in range(b) if S[e] == node] + [(e, IN) for e in range(b) if D[e] == node]
        events.sort()
        assert int(n_prior[i]) == len(events)
        got = [(int(e), int(d)) for e, d, m in zip(edges[i], dirs[i], mask[i]) if m]
        assert got == events[-k:]
        assert all(e < b for e, _ in got)  # never sees the scored edge or the future


def test_masked_rows_give_zero_attention():
    att = DiffAttention(d_q=6, d_kv=10, d_model=16, heads=2)
    q, kv = torch.randn(3, 6), torch.randn(3, 4, 10)
    mask = torch.tensor([[True] * 4, [False] * 4, [True, False, False, False]])
    out, a = att(q, kv, mask, return_attn=True)
    assert torch.isfinite(out).all()
    assert torch.all(a[1] == 0)
    assert torch.all(a[2, :, 1:] == 0)


def test_differential_map_is_difference_of_softmaxes():
    att = DiffAttention(d_q=6, d_kv=10, d_model=16, heads=2)
    q, kv, mask = torch.randn(2, 6), torch.randn(2, 5, 10), torch.ones(2, 5, dtype=torch.bool)
    _, a = att(q, kv, mask, return_attn=True)
    lam = float(att.lam().detach())
    # rows of each softmax sum to 1, so the differential map sums to 1 - lambda
    torch.testing.assert_close(a.sum(-1), torch.full_like(a.sum(-1), 1 - lam), atol=1e-5, rtol=0)


@pytest.mark.parametrize("attn", ["diff", "vanilla"])
def test_model_forward_backward(attn):
    b, k, n_num = 4, 6, 7
    m = TemporalEdgeModel(n_num, n_cur=3, n_fmt=2, num_mean=torch.zeros(n_num), num_std=torch.ones(n_num),
                          d_edge=16, d_time=8, d_model=32, heads=2, attn=attn)
    e = torch.randn(b, 16)
    batch = {"edge_emb": e}
    for side, role in (("u", OUT), ("v", IN)):
        batch.update({f"nb_emb_{side}": torch.randn(b, k, 16), f"dt_{side}": torch.randint(0, 1000, (b, k)),
                      f"dir_{side}": torch.randint(0, 2, (b, k)), f"mask_{side}": torch.rand(b, k) > 0.3,
                      f"n_{side}": torch.randint(0, 50, (b,)), f"role_{side}": torch.full((b,), role)})
    logit = m(batch)
    assert logit.shape == (b,)
    logit.sum().backward()
    assert all(p.grad is not None for n, p in m.named_parameters() if not n.startswith("edge_enc"))


def test_vanilla_and_diff_have_similar_size():
    d = sum(p.numel() for p in DiffAttention(73, 104, 128, 4).parameters())
    v = sum(p.numel() for p in VanillaAttention(73, 104, 128, 4).parameters())
    assert abs(d - v) / v < 0.01
