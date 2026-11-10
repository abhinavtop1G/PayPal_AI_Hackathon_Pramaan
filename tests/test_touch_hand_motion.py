"""Mouse drags must never pass as an enrolled phone profile.

Asha's touch profile was enrolled from HMOG phone gestures, which carry the phone's motion sensors. A laptop's mouse
sends none of those, and with them filled in as the training average, plain mouse swipes used to score as
"Looks like Asha's hands" about a third of the time on the Live capture page. Runs on the files shipped in the repo
(demo gesture pack + saved calibration), on a CPU, without the HMOG dataset.
"""
import json
import math
import os
import random
from pathlib import Path

import pytest

PACK = Path("ml/auth/artifacts/demo_gestures.json")
CALIB = "ml/auth/artifacts/bio_calib.pkl"
MOTION_FEATURES = ("acc_mean", "acc_std", "acc_pre", "acc_resist", "gyr_mean", "gyr_std", "gyr_pre", "gyr_resist")

pytestmark = pytest.mark.skipif(not (PACK.exists() and Path("ml/models/biometrics/artifacts/hmog_bilstm.pt").exists()),
                                reason="needs the shipped touch model and demo gesture pack")


@pytest.fixture(scope="module")
def pack():
    return json.loads(PACK.read_text())


@pytest.fixture(scope="module")
def scorer(pack):
    pytest.importorskip("torch")
    os.environ.setdefault("BIO_CALIB", CALIB)
    import ml.models.biometrics.scorer as sc
    sc.CALIB = Path(CALIB)
    s = sc.BioScorer("cpu")
    assert s.enroll("asha", pack["enrolment"])["hand_motion"] is True
    return s


def mouse_window(rng: random.Random, n: int = 10) -> list[dict]:
    """What the web SDK sends for scroll-like mouse drags on the 17 x 26 rem pad: geometry and timing, no size or motion."""
    from ml.models.biometrics.data import FEATURES
    W, H = 340.0, 520.0
    out = []
    for _ in range(n):
        dur = rng.uniform(150, 700)
        x0, y0 = rng.uniform(0.2, 0.8) * W, rng.uniform(0.5, 0.85) * H
        x1, y1 = x0 + rng.gauss(0, 0.05) * W, y0 - rng.uniform(0.2, 0.5) * H
        path = math.hypot(x1 - x0, y1 - y0) * 1080 / W
        g = dict.fromkeys(FEATURES)
        g.update(log_duration_ms=math.log1p(dur), log_gap_ms=math.log1p(rng.uniform(400, 2500)), dx=(x1 - x0) / W,
                 dy=(y1 - y0) / H, log_path_len=math.log1p(path), log_speed=math.log1p(path / dur * 1000),
                 log_n_points=math.log1p(dur / rng.uniform(7, 16)), x0=x0 / W, y0=y0 / H, is_tap=0.0, rotated=0.0)
        out.append(g)
    return out


def without_motion(window: list[dict]) -> list[dict]:
    return [{k: (None if k in MOTION_FEATURES else v) for k, v in g.items()} for g in window]


def test_real_phone_windows_are_still_scored(scorer, pack):
    own = [scorer.verify("asha", w[-10:]) for w in pack["windows"]["normal"]]
    other = [scorer.verify("asha", w[-10:]) for w in pack["windows"]["remote"]]
    assert all(r["comparable"] and r["fused_score"] is not None for r in own + other)
    assert sum(r["matches_profile"] for r in own) >= 0.9 * len(own)
    assert sum(r["matches_profile"] for r in other) <= 0.25 * len(other)


def test_mouse_swipes_never_pass_as_asha(scorer):
    rng = random.Random(0)
    for _ in range(40):
        r = scorer.verify("asha", mouse_window(rng))
        assert not r["comparable"] and not r["matches_profile"]
        assert r["behavioural_deviation"] is None and r["fused_score"] is None and r["reason"]
        assert r["profile_hand_motion"] is True and r["window_hand_motion"] is False


def test_her_own_gestures_without_motion_get_no_verdict(scorer, pack):
    r = scorer.verify("asha", without_motion(pack["windows"]["normal"][0][-10:]))
    assert not r["comparable"] and not r["matches_profile"]


def test_a_mouse_enrolled_profile_is_compared_with_mouse_windows(scorer):
    rng = random.Random(1)
    assert scorer.enroll("mouse-user", mouse_window(rng, 24))["hand_motion"] is False
    r = scorer.verify("mouse-user", mouse_window(rng))
    assert r["comparable"] and isinstance(r["behavioural_deviation"], float)


def test_engine_leaves_bio_dev_missing_for_mouse_gestures(scorer):
    from ml.auth.engine import AuthEngine
    eng = AuthEngine.__new__(AuthEngine)
    eng.bio, eng.typing, eng.payee = scorer, None, None
    req = {"user_id": "asha", "behaviour": {"gestures": mouse_window(random.Random(2), 12)}}
    eng._enrich(req)
    assert req["behaviour"].get("bio_dev") is None
