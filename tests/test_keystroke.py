"""Keystroke dynamics: data layout, encoder, protocol, scorer, and the typing signal in the auth API."""
from pathlib import Path

import numpy as np
import pytest
import torch

from ml.models.keystroke.data import COLUMNS, KEYS, PATH
from ml.models.keystroke.model import KeystrokeEncoder, sequence
from ml.models.keystroke.protocol import profile_manhattan, score, score_manhattan, sims

ART = Path("ml/models/keystroke/artifacts/keystroke_cnn.pt")
needs_data = pytest.mark.skipif(not PATH.exists(), reason="CMU keystroke CSV not in DATA/keystroke/")
needs_model = pytest.mark.skipif(not ART.exists(), reason="run python -m ml.models.keystroke.evaluate first")


def test_columns_follow_key_order():
    assert len(COLUMNS) == 31 and len(KEYS) == 11
    assert COLUMNS[:3] == ["H.period", "DD.period.t", "UD.period.t"]
    assert COLUMNS[-4:] == ["H.l", "DD.l.Return", "UD.l.Return", "H.Return"]


def test_sequence_layout():
    raw = torch.arange(1, 32, dtype=torch.float32)[None] / 100     # 0.01 ... 0.31 s
    s = sequence(raw)
    assert s.shape == (1, 11, 4)
    assert torch.isclose(s[0, 0, 0], torch.log(torch.tensor(0.01)))           # H.period
    assert torch.isclose(s[0, 0, 1], torch.log1p(torch.tensor(0.02 * 10)))    # DD.period.t
    assert torch.isclose(s[0, 10, 0], torch.log(torch.tensor(0.31)))          # H.Return (last key)
    assert s[0, 10, 1:].abs().sum() == 0 and s[0, :10, 3].eq(1).all()          # last key: no next-key channels


def test_negative_up_down_keeps_sign():
    raw = torch.full((1, 31), 0.1)
    raw[0, 2] = -0.05                                                          # next key pressed before release
    assert sequence(raw)[0, 0, 2] < 0


def test_encoder_unit_embeddings():
    m = KeystrokeEncoder(ch=16, emb=8).fit_standardiser(torch.rand(64, 31) * 0.3 + 0.01).eval()
    e = m(torch.rand(5, 31) * 0.3 + 0.01)
    assert e.shape == (5, 8) and torch.allclose(e.norm(dim=-1), torch.ones(5), atol=1e-5)


def test_manhattan_prefers_owner():
    rng = np.random.default_rng(0)
    own = rng.normal(0.15, 0.01, (50, 31))
    other = rng.normal(0.25, 0.01, (50, 31))
    prof = profile_manhattan(own[:40])
    assert score_manhattan(own[40:], prof).mean() > score_manhattan(other, prof).mean()


def test_protocol_scores_separable_users():
    rng = np.random.default_rng(1)
    raw = np.concatenate([rng.normal(0.1 + 0.05 * u, 0.005, (20, 31)) for u in range(3)])
    user = np.repeat(np.arange(3), 20)
    enrol = np.tile(np.arange(20) < 10, 3)
    s = sims("manhattan", np.arange(3), enrol, ~enrol, user, raw=raw)
    assert score(s, user[~enrol])["eer"] == 0.0


@needs_data
def test_training_dry_run(tmp_path, monkeypatch):
    from ml.models.keystroke import train
    monkeypatch.setattr(train, "CKPT_DIR", tmp_path)
    monkeypatch.setattr(train, "REPORT_DIR", tmp_path)
    res = train.main(["--epochs", "1", "--max-steps", "5", "--tag", "_test"])
    assert 0 <= res["valid"]["eer"] <= 1 and (tmp_path / "cnn_test_s0.pt").exists()


@needs_model
def test_scorer_round_trip():
    from ml.models.keystroke.scorer import KeystrokeScorer
    sc = KeystrokeScorer("cpu")
    rng = np.random.default_rng(2)
    base = rng.uniform(0.05, 0.3, 31).astype("float32")
    sc.enroll("u", base * np.exp(rng.normal(0, 0.05, (20, 31))))
    own = sc.verify("u", (base * np.exp(rng.normal(0, 0.05, 31))).tolist())
    other = sc.verify("u", (base[::-1] * 2).tolist())
    assert own["typing_deviation"] < other["typing_deviation"]
    with pytest.raises(ValueError):
        sc.enroll("v", [[0.1] * 31] * 3)       # too few attempts
    with pytest.raises(ValueError):
        sc.verify("u", [0.1] * 30)              # wrong length
    with pytest.raises(KeyError):
        sc.verify("nobody", base.tolist())


@needs_model
def test_auth_api_uses_typing():
    import os
    from fastapi.testclient import TestClient
    os.environ["PRAMAAN_SERVICES"] = "keystroke,auth"
    os.environ["PRAMAAN_AUDIT_DB"] = "checkpoints/test_audit_ks.sqlite"
    from backend.app import app
    try:
        with TestClient(app) as c:
            assert c.get("/health").json()["auth"]["typing_biometrics"] is True
            own = c.post("/v1/auth/demo/custom", json={"behaviour": {"typing_profile": "normal"}}).json()["response"]
            other = c.post("/v1/auth/demo/custom", json={"behaviour": {"typing_profile": "remote"}}).json()["response"]
            bot = c.post("/v1/auth/demo/custom", json={"behaviour": {"typing_profile": "bot"}}).json()["response"]
            assert own["features"]["typing_dev"] is not None
            assert own["features"]["typing_dev"] < min(other["features"]["typing_dev"], bot["features"]["typing_dev"])
            bad = c.post("/v1/keystroke/enroll", json={"user_id": "x", "attempts": [[0.1] * 31] * 2})
            assert bad.status_code == 422
    finally:
        os.environ.pop("PRAMAAN_SERVICES", None)
