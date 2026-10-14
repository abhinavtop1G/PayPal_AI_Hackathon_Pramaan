"""HMOG -> one row per touch gesture (DOWN ... UP), with touch dynamics and HMOG-style hand-motion
features from the accelerometer/gyroscope around the touch. Reads straight from the nested zips
(no extraction) and caches DATA/hmog/gestures.parquet.

    python -m ml.models.biometrics.data          # build cache (~100 user zips, multiprocess)

Column layouts follow public_dataset/data_description.pdf (CSV files have no header).
"""
import io
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ZIP = Path("DATA/hmog_dataset.zip")
CACHE = Path("DATA/hmog/gestures.parquet")
SCREEN_W, SCREEN_H = 1080.0, 1920.0  # all HMOG sessions were recorded on the same phone model

TOUCH_COLS = ["systime", "event_time", "activity_id", "pointer_count", "pointer_id", "action_id", "x", "y",
              "pressure", "size", "orientation"]
SENSOR_COLS = ["systime", "event_time", "activity_id", "x", "y", "z", "orientation"]
ACTIVITY_COLS = ["activity_id", "subject", "session", "start", "end", "rel_start", "rel_end", "scenario", "task", "content"]
DOWN, UP, MOVE = {0, 5}, {1, 6}, {2}
PRE_MS, POST_MS = 100, 100  # sensor context around a touch

# Pressure is constant 1.0 on the HMOG phone, so it is computed but not used as a feature.
# Accelerometer magnitude includes gravity (~9.2 m/s^2) despite the description; std/resist carry the signal.
FEATURES = [
    "log_duration_ms", "log_gap_ms", "size_mean", "size_max",
    "dx", "dy", "log_path_len", "log_speed", "log_n_points", "x0", "y0", "is_tap",
    "acc_mean", "acc_std", "acc_pre", "acc_resist", "gyr_mean", "gyr_std", "gyr_pre", "gyr_resist", "rotated",
]


def _read(z: zipfile.ZipFile, name: str, cols: list[str]) -> pd.DataFrame:
    try:
        raw = z.read(name)
    except KeyError:
        return pd.DataFrame(columns=cols)
    if not raw.strip():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(io.BytesIO(raw), header=None, on_bad_lines="skip")
    df = df.iloc[:, : len(cols)]
    df.columns = cols[: df.shape[1]]
    return df.apply(pd.to_numeric, errors="coerce").dropna(subset=[df.columns[0]])


def extract_gestures(touch: pd.DataFrame) -> pd.DataFrame:
    """Single-pointer DOWN..UP sequences -> one row each with touch-dynamics features."""
    t = touch[(touch["pointer_id"] == 0)].sort_values(["systime", "event_time"], kind="stable").reset_index(drop=True)
    if t.empty:
        return pd.DataFrame()
    is_down = t["action_id"].isin(DOWN)
    gid = is_down.cumsum()
    t = t[gid > 0].assign(gid=gid[gid > 0])
    # keep rows up to and including the first UP of each gesture
    is_up = t["action_id"].isin(UP)
    ups_before = is_up.groupby(t["gid"]).cumsum() - is_up
    t = t[ups_before == 0]
    step = np.hypot(t["x"].diff(), t["y"].diff()).where(t["gid"].eq(t["gid"].shift()), 0.0)
    g = t.assign(step=step).groupby("gid")
    out = pd.DataFrame({
        "activity_id": g["activity_id"].first(),
        "t_down": g["systime"].first(),
        "t_up": g["systime"].last(),
        "ended": g["action_id"].last().isin(UP),
        "multi_touch": g["pointer_count"].max() > 1,
        "pressure_mean": g["pressure"].mean(), "pressure_max": g["pressure"].max(),
        "pressure_std": g["pressure"].std().fillna(0),
        "size_mean": g["size"].mean(), "size_max": g["size"].max(),
        "x0": g["x"].first() / SCREEN_W, "y0": g["y"].first() / SCREEN_H,
        "dx": (g["x"].last() - g["x"].first()) / SCREEN_W, "dy": (g["y"].last() - g["y"].first()) / SCREEN_H,
        "path_len": g["step"].sum(), "n_points": g.size(),
        "rotated": (g["orientation"].first() != 0).astype(float),
    })
    out = out[out["ended"] & ~out["multi_touch"]].drop(columns=["ended", "multi_touch"])
    dur = (out["t_up"] - out["t_down"]).clip(lower=1)
    out = out[dur < 5000]
    dur = dur[out.index]
    out["log_duration_ms"] = np.log1p(dur)
    out["log_gap_ms"] = np.log1p((out["t_down"] - out["t_up"].shift()).clip(lower=0, upper=60_000)).fillna(np.log1p(60_000))
    out["log_path_len"] = np.log1p(out["path_len"])
    out["log_speed"] = np.log1p(out["path_len"] / dur * 1000)
    out["log_n_points"] = np.log1p(out["n_points"])
    out["is_tap"] = (out["path_len"] < 20).astype(float)
    return out.reset_index(drop=True)


def _window_stats(t_sensor: np.ndarray, mag: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    """Mean/std of `mag` over [lo, hi] per window via prefix sums (sensor sorted by time)."""
    cs = np.concatenate([[0.0], np.cumsum(mag)])
    cs2 = np.concatenate([[0.0], np.cumsum(mag ** 2)])
    a, b = np.searchsorted(t_sensor, lo, "left"), np.searchsorted(t_sensor, hi, "right")
    n = (b - a).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = (cs[b] - cs[a]) / n
        var = (cs2[b] - cs2[a]) / n - mean ** 2
    return np.where(n > 0, mean, np.nan), np.where(n > 1, np.sqrt(np.clip(var, 0, None)), np.nan)


def add_motion_features(gest: pd.DataFrame, sensor: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if sensor.empty or gest.empty:
        for s in ("mean", "std", "pre", "resist"):
            gest[f"{prefix}_{s}"] = np.nan
        return gest
    s = sensor.sort_values("systime", kind="stable")
    ts = s["systime"].to_numpy(float)
    mag = np.sqrt(s["x"].to_numpy(float) ** 2 + s["y"].to_numpy(float) ** 2 + s["z"].to_numpy(float) ** 2)
    d, u = gest["t_down"].to_numpy(float), gest["t_up"].to_numpy(float)
    m, sd = _window_stats(ts, mag, d, u + POST_MS)
    pre, _ = _window_stats(ts, mag, d - PRE_MS, d)
    gest[f"{prefix}_mean"], gest[f"{prefix}_std"], gest[f"{prefix}_pre"] = m, sd, pre
    gest[f"{prefix}_resist"] = m - pre  # HMOG "grasp resistance": how much the tap moves the phone
    return gest


def process_user(zip_path: str, member: str) -> pd.DataFrame:
    outer = zipfile.ZipFile(zip_path)
    inner = zipfile.ZipFile(io.BytesIO(outer.read(member)))
    sessions = sorted({n.split("/")[1] for n in inner.namelist() if n.count("/") >= 2 and "_session_" in n})
    frames = []
    for sess in sessions:
        user = sess.split("_")[0]
        base = f"{user}/{sess}/"
        touch = _read(inner, base + "TouchEvent.csv", TOUCH_COLS)
        g = extract_gestures(touch)
        if g.empty:
            continue
        g = add_motion_features(g, _read(inner, base + "Accelerometer.csv", SENSOR_COLS), "acc")
        g = add_motion_features(g, _read(inner, base + "Gyroscope.csv", SENSOR_COLS), "gyr")
        act = _read(inner, base + "Activity.csv", ACTIVITY_COLS).drop_duplicates("activity_id", keep="last")
        g = g.merge(act[["activity_id", "scenario", "task"]], on="activity_id", how="left")
        g.insert(0, "session", int(sess.rsplit("_", 1)[1]))
        g.insert(0, "user", int(user))
        frames.append(g)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build(zip_path: Path = ZIP, cache: Path = CACHE, workers: int = 8) -> pd.DataFrame:
    members = [n for n in zipfile.ZipFile(zip_path).namelist() if n.endswith(".zip")]
    with ProcessPoolExecutor(workers) as ex:
        parts = list(ex.map(process_user, [str(zip_path)] * len(members), members))
    df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    df = df.sort_values(["user", "session", "t_down"], kind="stable").reset_index(drop=True)
    keep = ["user", "session", "activity_id", "scenario", "task", "t_down", "t_up"] + FEATURES
    df = df[keep]
    df[FEATURES] = df[FEATURES].astype("float32")
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def load_gestures(refresh: bool = False) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    return build()


if __name__ == "__main__":
    import time
    t0 = time.time()
    df = build()
    print(f"{len(df):,} gestures, {df['user'].nunique()} users, {df.groupby(['user', 'session']).ngroups} sessions "
          f"in {time.time() - t0:.0f}s")
    print(df[FEATURES].describe().T[["mean", "std", "min", "max"]].round(3).to_string())
    print("missing:", df[FEATURES].isna().mean().round(3)[lambda s: s > 0].to_dict())
