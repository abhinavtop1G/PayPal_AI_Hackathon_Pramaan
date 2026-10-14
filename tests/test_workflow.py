import numpy as np
import pandas as pd
import pytest

from ml.models.workflow.data import CAT_COLS, STAGES, SeqData
from ml.models.workflow.metrics import alert_outcomes, first_alert, threshold_for_budget

F = 6


def _seq(n_sessions=6, T=5, scam_every=2, seed=0) -> SeqData:
    rng = np.random.default_rng(seed)
    is_scam = np.arange(n_sessions) % scam_every == 0
    stage = [np.array([0, 1, 2, 4, 4]) if s else np.zeros(T, int) for s in is_scam]
    pay = [np.array([False, False, True, True, True]) for _ in range(n_sessions)]
    return SeqData(
        num=[rng.normal(size=(T, F)).astype("float32") for _ in range(n_sessions)],
        cat=[np.zeros((T, 4), "int64") for _ in range(n_sessions)],
        stage=stage, is_payment=pay, ts=[np.arange(T, dtype=float) * 10 for _ in range(n_sessions)],
        amount=[np.where(p, 100.0, 0.0) for p in pay],
        sessions=pd.DataFrame({"is_scam": is_scam, "typology": np.where(is_scam, "digital_arrest", "routine"),
                               "extraction_ts": np.where(is_scam, 30.0, np.nan), "typology_id": 0}),
        num_names=[f"f{i}" for i in range(F)],
    )


def test_alerts_only_at_payment_attempts_and_timing():
    d = _seq()
    # scores high everywhere except payment attempts of session 0 until the last one
    scores = [np.ones(5) for _ in range(6)]
    scores[0] = np.array([1, 1, 0, 0, 1.0])
    idx = first_alert(scores, d, 0.5)
    assert idx[0] == 4  # first *payment* attempt above threshold, not event 0
    out = alert_outcomes(scores, d, 0.5)
    # session 0 alerts at ts=40 > extraction_ts=30 -> caught, but not in time; sessions 2, 4 caught at ts=20
    assert out["scams_caught_any_time"] == 1.0
    assert out["scams_caught_in_time"] == pytest.approx(2 / 3, abs=1e-3)
    assert out["benign_false_alert_rate"] == 1.0


def test_money_saved_counts_payments_from_alert_onwards():
    d = _seq(n_sessions=2)
    scores = [np.array([0, 0, 0, 1, 1.0]), np.zeros(5)]
    out = alert_outcomes(scores, d, 0.5)
    # scam session 0: scam payments at idx 2 (pretext), 3, 4 (extraction) = 300; alert at idx 3 saves 200
    assert out["money_saved_pct"] == pytest.approx(100 * 200 / 300, abs=0.01)


def test_threshold_respects_budget():
    d = _seq(n_sessions=200, scam_every=4)
    rng = np.random.default_rng(1)
    scores = [rng.random(5) for _ in range(200)]
    thr = threshold_for_budget(scores, d, 0.05)
    assert alert_outcomes(scores, d, thr)["benign_false_alert_rate"] <= 0.05


def test_gru_is_causal():
    torch = pytest.importorskip("torch")
    from ml.models.workflow.model import WorkflowGRU
    m = WorkflowGRU(F, torch.zeros(F), torch.ones(F), d=16).eval()
    num = torch.randn(2, 8, F)
    cat = torch.zeros(2, 8, 4, dtype=torch.long)
    a1, s1, t1 = m(num, cat)
    num2, cat2 = num.clone(), cat.clone()
    num2[:, 5:] = torch.randn(2, 3, F)          # change the future
    cat2[:, 5:, 0] = len(CAT_COLS["event"]) - 1
    a2, s2, t2 = m(num2, cat2)
    torch.testing.assert_close(a1[:, :5], a2[:, :5])
    torch.testing.assert_close(s1[:, :5], s2[:, :5])
    assert s1.shape[-1] == len(STAGES)
    assert all(g.dropout == 0 for g in m.grus)  # cuDNN RNN dropout crashes at exit on Windows
