"""Final HMOG evaluation: LSTM seeds vs window-statistics baselines vs LSTM+LDA score fusion.

    python -m ml.models.biometrics.evaluate      # after training seeds with models.biometrics.train

Writes reports/biometrics_hmog.json and reports/biometrics_hmog.md (test users; valid shown for reference).
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

from .baseline import window_stats
from .data import FEATURES, load_gestures
from .metrics import fuse, score, similarity
from .model import GestureEncoder
from .train import CKPT_DIR, EVAL_LENGTHS, embed
from .windows import make_windows, prepare

REPORT_DIR = Path("ml/reports")
KEYS = ["eer", "per_user_eer_mean", "eer_sitting", "eer_walking"]


def _agg(rs: list[dict]) -> dict:
    return {k: (float(np.mean([r[k] for r in rs])), float(np.std([r[k] for r in rs], ddof=1)) if len(rs) > 1 else 0.0)
            for k in KEYS}


def main(split_seed: int = 0):
    device = torch.device("cuda")
    df = load_gestures()
    split, _, z = prepare(df, split_seed)
    part = {k: df["user"].isin(v).to_numpy() for k, v in split.items()}
    ckpts = sorted(CKPT_DIR.glob("hmog_lstm_s*.pt"))
    models = []
    for p in ckpts:
        ck = torch.load(p, weights_only=False)
        a = ck["args"]
        m = GestureEncoder(len(FEATURES), a["hidden"], emb=a["emb"], dropout=a["dropout"]).to(device)
        m.load_state_dict(ck["state_dict"])
        models.append(m)
    print(f"{len(models)} LSTM checkpoints: {[p.name for p in ckpts]}")

    res = {s: {} for s in ("valid", "test")}
    for n in EVAL_LENGTHS:
        tr = make_windows(df[part["train"]], z[part["train"]], n, stride=max(1, n // 2))
        s_tr = window_stats(tr.x)
        mu, sd = s_tr.mean(0), s_tr.std(0) + 1e-6
        lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto").fit((s_tr - mu) / sd, tr.user)
        for s in res:
            w = make_windows(df[part[s]], z[part[s]], n, stride=n)
            stats = (window_stats(w.x) - mu) / sd
            sim_cos, owner, probe = similarity(stats, w.user, w.session)
            sim_lda, _, _ = similarity(lda.transform(stats), w.user, w.session)
            scen = w.scenario[probe]
            lstm_runs, fused_runs = [], []
            for m in models:
                sim_lstm, _, _ = similarity(embed(m, w.x, device), w.user, w.session)
                lstm_runs.append(score(sim_lstm, owner, scen))
                fused_runs.append(score(fuse(sim_lstm, sim_lda), owner, scen))
            res[s][f"n{n}"] = {
                "stats_cosine": _agg([score(sim_cos, owner, scen)]),
                "stats_lda": _agg([score(sim_lda, owner, scen)]),
                "bilstm": _agg(lstm_runs),
                "bilstm+lda_fused": _agg(fused_runs),
                "n_probe_windows": int(len(owner)), "n_users": int(sim_lda.shape[1]),
            }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "biometrics_hmog.json").write_text(json.dumps({"seeds": len(models), **res}, indent=2))

    names = {"stats_cosine": "Window stats + cosine", "stats_lda": "Window stats + LDA",
             "bilstm": f"BiLSTM gesture encoder ({len(models)} seeds)", "bilstm+lda_fused": "BiLSTM + LDA score fusion"}
    fmt = lambda v: f"{100 * v[0]:.1f}" + (f" ± {100 * v[1]:.1f}" if v[1] else "")  # noqa: E731
    lines = [
        "# HMOG continuous authentication — open-set verification",
        "",
        f"Users split 70/15/15 (train/valid/test, disjoint). Test users: {res['test']['n10']['n_users']}. "
        "Profile = sessions 1–12, probes = sessions 13–24; impostors = all other test users. "
        "EER in % (lower is better); per-user = mean of each user's own EER (per-user thresholds).",
        "",
        "| window | model | test EER | per-user EER | sitting | walking | valid EER |",
        "|---|---|---|---|---|---|---|",
    ]
    for n in EVAL_LENGTHS:
        for k, label in names.items():
            t, v = res["test"][f"n{n}"][k], res["valid"][f"n{n}"][k]
            lines.append(f"| {n} gestures | {label} | {fmt(t['eer'])} | {fmt(t['per_user_eer_mean'])} | "
                         f"{fmt(t['eer_sitting'])} | {fmt(t['eer_walking'])} | {fmt(v['eer'])} |")
    (REPORT_DIR / "biometrics_hmog.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
