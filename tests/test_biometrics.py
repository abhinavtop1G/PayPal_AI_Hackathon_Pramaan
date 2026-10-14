import numpy as np
import pandas as pd
import pytest

from ml.models.biometrics.data import FEATURES, TOUCH_COLS, extract_gestures
from ml.models.biometrics.metrics import eer, verify
from ml.models.biometrics.windows import make_windows


def _touch(rows):
    """rows: (systime, action, x, y, pointer_id, pointer_count)"""
    return pd.DataFrame([{**dict.fromkeys(TOUCH_COLS, 0), "systime": t, "event_time": t, "activity_id": 7,
                          "action_id": a, "x": x, "y": y, "pointer_id": pid, "pointer_count": pc,
                          "pressure": 1.0, "size": 0.02} for t, a, x, y, pid, pc in rows])


def test_gesture_segmentation():
    g = extract_gestures(_touch([
        (1000, 0, 100, 100, 0, 1), (1010, 2, 110, 100, 0, 1), (1020, 1, 120, 100, 0, 1),   # swipe 20px
        (1500, 0, 300, 300, 0, 1), (1560, 1, 300, 300, 0, 1),                              # tap
        (2000, 0, 50, 50, 0, 1), (2010, 2, 60, 60, 0, 1),                                  # never released
    ]))
    assert len(g) == 2
    np.testing.assert_allclose(g["path_len"], [20.0, 0.0])
    np.testing.assert_allclose(np.expm1(g["log_duration_ms"]), [20, 60], rtol=1e-6)
    np.testing.assert_allclose(np.expm1(g["log_gap_ms"].iloc[1]), 480, rtol=1e-6)  # 1500 - 1020
    assert g["is_tap"].tolist() == [0.0, 1.0]


def test_multitouch_gestures_dropped():
    g = extract_gestures(_touch([(1000, 0, 1, 1, 0, 1), (1005, 5, 9, 9, 1, 2), (1010, 2, 2, 2, 0, 2),
                                 (1020, 1, 3, 3, 0, 2), (2000, 0, 5, 5, 0, 1), (2050, 1, 5, 5, 0, 1)]))
    assert len(g) == 1 and g["t_down"].iloc[0] == 2000


def test_windows_never_cross_sessions():
    df = pd.DataFrame({"user": [1] * 7 + [2] * 5, "session": [1] * 4 + [2] * 3 + [1] * 5, "scenario": 1})
    z = np.arange(12, dtype="float32")[:, None].repeat(len(FEATURES), 1)
    w = make_windows(df, z, n=3, stride=1)
    assert len(w.x) == 2 + 1 + 3
    for x, u, s in zip(w.x, w.user, w.session):
        rows = x[:, 0].astype(int)
        assert (df.loc[rows, "user"] == u).all() and (df.loc[rows, "session"] == s).all()


def test_eer_known_values():
    assert eer(np.array([0.9, 0.8, 0.7]), np.array([0.1, 0.2, 0.3])) == 0.0
    assert eer(np.array([0.1, 0.2]), np.array([0.8, 0.9])) == pytest.approx(1.0)
    rng = np.random.default_rng(0)
    assert abs(eer(rng.normal(size=20000), rng.normal(size=20000)) - 0.5) < 0.02


def test_verify_separable_users_gives_zero_eer():
    rng = np.random.default_rng(0)
    centres = np.eye(4) * 10
    user = np.repeat(np.arange(4), 40)
    session = np.tile(np.r_[np.full(20, 3), np.full(20, 15)], 4)  # enrol in session 3, probe in 15
    emb = centres[user] + rng.normal(scale=0.1, size=(len(user), 4))
    r = verify(emb, user, session)
    assert r["eer"] == 0.0 and r["n_users"] == 4 and r["n_probe_windows"] == 80


def test_encoder_variable_length_and_no_cudnn_dropout():
    torch = pytest.importorskip("torch")
    from ml.models.biometrics.model import GestureEncoder
    m = GestureEncoder(len(FEATURES), hidden=16, emb=8, dropout=0.4).eval()
    for n in (5, 10, 20):
        e = m(torch.randn(3, n, len(FEATURES)))
        assert e.shape == (3, 8)
        torch.testing.assert_close(e.norm(dim=-1), torch.ones(3))
    # cuDNN inter-layer LSTM dropout crashes the process at exit on Windows (torch 2.14 / cuDNN 9.10)
    assert all(lstm.dropout == 0 for lstm in m.lstms)
