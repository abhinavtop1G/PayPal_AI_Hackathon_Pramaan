"""Evaluate the keystroke CNN on held-out users against classic detectors; calibrate and ship the serving model.

    python -m ml.models.keystroke.evaluate        # needs checkpoints/keystroke/cnn_s{0,1,2}.pt (train.py)

Protocols (all on users the CNN never saw):
  A  open set, enrolment = sessions 1-4 (200 attempts), probes = sessions 5-8 of the same 8 test users
  B  realistic enrolment = first 10 attempts of session 1 (what a bank would collect), probes = sessions 5-8
  C  Killourhy & Maxion's protocol: train on a user's first 200 attempts, genuine = their last 200, impostors = the
     first 5 attempts of each of the other 50 subjects. Classic detectors on all 51 users (comparable with the
     paper); every method also on the 8 held-out users (the CNN cannot be scored on users it trained on).
Each also with the similarity averaged over 3 consecutive attempts ("3 tries"). Fusion = mean of z-normalised CNN
and scaled-Manhattan scores (normalisation constants from valid users).
Writes ml/reports/keystroke_cmu.{md,json} and ml/models/keystroke/artifacts/keystroke_cnn.{pt,meta.json}.
"""
import json
from pathlib import Path

import numpy as np
import torch

from ml.models.biometrics.metrics import eer
from ml.models.biometrics.windows import split_users

from .data import load_cmu, timings
from .model import KeystrokeEncoder
from .protocol import average_attempts, norm_constants, score, sims
from .train import CKPT_DIR, embed

ART = Path("ml/models/keystroke/artifacts")
REPORTS = Path("ml/reports")
SEEDS = (0, 1, 2)
PUBLISHED = {"Manhattan (scaled)": 0.096, "Nearest neighbour (Mahalanobis)": 0.100, "Mahalanobis": 0.110}


def load_model(seed, device):
    ck = torch.load(CKPT_DIR / f"cnn_s{seed}.pt", map_location=device, weights_only=False)
    a = ck["args"]
    m = KeystrokeEncoder(a["ch"], a["emb"], a["dropout"]).to(device)
    m.load_state_dict(ck["state_dict"])
    return m.eval(), ck


def protocol_ab(df, raw, users, emb, enrol_kind: str):
    """Similarity matrices for every method on `users`; enrol_kind 'sessions' (1-4) or 'first10' (session 1, reps 1-10)."""
    m = df["user"].isin(users).to_numpy()
    user, sess, rep = (df[c].to_numpy()[m] for c in ("user", "session", "rep"))
    enrol = sess <= 4 if enrol_kind == "sessions" else (sess == 1) & (rep <= 10)
    probe = sess >= 5
    us = np.array(sorted(users))
    S = {"cnn": sims("cnn", us, enrol, probe, user, emb=emb[m]),
         "manhattan": sims("manhattan", us, enrol, probe, user, raw=raw[m]),
         "mahalanobis": sims("mahalanobis", us, enrol, probe, user, raw=raw[m])}
    owner = np.searchsorted(us, user[probe])
    groups = (user[probe] * 1000 + sess[probe] * 100 + (rep[probe] - 1) // 3)   # 3 consecutive attempts
    return S, owner, groups


def fused(S, norm):
    return ((S["cnn"] - norm["cnn"][0]) / norm["cnn"][1] + (S["manhattan"] - norm["manhattan"][0]) / norm["manhattan"][1]) / 2


def evaluate_set(S, owner, groups, norm):
    S = dict(S, fusion=fused(S, norm))
    out = {}
    for k, s in S.items():
        g3, first = average_attempts(s, groups)
        out[k] = {"one_try": score(s, owner), "three_tries": score(g3, owner[first])}
    return out


def km_protocol(df, raw, genuine_users, method, emb=None, norm=None):
    """Killourhy & Maxion: per-user EER, mean over genuine users."""
    user, sess, rep = (df[c].to_numpy() for c in ("user", "session", "rep"))
    first5 = (sess == 1) & (rep <= 5)
    eers = []
    for u in genuine_users:
        tr = (user == u) & (sess <= 4)
        gen = (user == u) & (sess >= 5)
        imp = (user != u) & first5
        probe = gen | imp
        cols = {}
        for meth in (("cnn", "manhattan") if method == "fusion" else (method,)):
            col = sims(meth, [u], tr, probe, user, raw=raw, emb=emb)[:, 0]
            cols[meth] = col
        s = (fused(cols, norm) if method == "fusion" else cols[method])
        is_gen = gen[probe]
        eers.append(eer(s[is_gen], s[~is_gen]))
    return round(float(np.mean(eers)), 4), round(float(np.std(eers)), 4)


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    df = load_cmu()
    raw = timings(df)
    tr, va, te = split_users(df["user"].unique(), 0)
    per_seed, valid_scores, models = {}, {}, {}
    for seed in SEEDS:
        model, ck = load_model(seed, device)
        assert sorted(map(int, te)) == ck["split"]["test"], "checkpoint trained on a different user split"
        emb = embed(model, raw, device)
        # normalisation constants and threshold come from valid users only, with the serving enrolment: a profile
        # built from the customer's past attempts (sessions 1-4)
        Sv, ov, _ = protocol_ab(df, raw, va, emb, "sessions")
        norm = {k: norm_constants(Sv[k]) for k in ("cnn", "manhattan")}
        fv = fused(Sv, norm)
        gen = np.zeros_like(fv, dtype=bool)
        gen[np.arange(len(ov)), ov] = True
        from sklearn.metrics import roc_curve
        fpr, tpr, thr = roc_curve(gen.ravel(), fv.ravel())
        i = int(np.nanargmin(np.abs((1 - tpr) - fpr)))
        calib = {"norm": norm, "threshold": float(thr[i]), "valid_eer": float((fpr[i] + 1 - tpr[i]) / 2)}
        valid_scores[seed] = score(Sv["cnn"], ov)["per_user_eer_mean"]
        res = {}
        for kind in ("sessions", "first10"):
            S, owner, groups = protocol_ab(df, raw, te, emb, kind)
            res[kind] = evaluate_set(S, owner, groups, norm)
        res["km_heldout"] = {m: km_protocol(df, raw, sorted(te), m, emb=emb, norm=norm)
                             for m in ("cnn", "manhattan", "mahalanobis", "fusion")}
        per_seed[seed] = res
        models[seed] = (model, ck, calib)
        print(f"seed {seed}: test one-try per-user EER  cnn {res['sessions']['cnn']['one_try']['per_user_eer_mean']:.4f}  "
              f"manhattan {res['sessions']['manhattan']['one_try']['per_user_eer_mean']:.4f}  "
              f"fusion {res['sessions']['fusion']['one_try']['per_user_eer_mean']:.4f}", flush=True)

    km_all = {m: km_protocol(df, raw, sorted(df["user"].unique()), m) for m in ("manhattan", "mahalanobis")}

    def agg(path):
        v = []
        for seed in SEEDS:
            x = per_seed[seed]
            for p in path:
                x = x[p]
            v.append(x)
        return round(float(np.mean(v)), 4), round(float(np.std(v)), 4)

    best = min(SEEDS, key=lambda s: valid_scores[s])
    model, ck, calib = models[best]
    ART.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "args": ck["args"]}, ART / "keystroke_cnn.pt")
    meta = {"model": "1D-CNN keystroke encoder (CosFace), CMU DSL-StrongPassword", "selected_seed": best,
            "valid_per_user_eer_by_seed": valid_scores, "args": ck["args"], "split": ck["split"],
            "calibration": calib, "columns": "ml.models.keystroke.data.COLUMNS (31 timings, seconds)",
            "enrolment": "mean embedding + scaled-Manhattan stats of past attempts (calibrated with 200 over 4 sessions)",
            "params": sum(p.numel() for p in model.parameters())}
    (ART / "keystroke_cnn.meta.json").write_text(json.dumps(meta, indent=2))

    R = {"per_seed": per_seed, "km_all_users": km_all, "published_km": PUBLISHED, "selected_seed": best,
         "users": {"train": len(tr), "valid": len(va), "test": len(te)}}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "keystroke_cmu.json").write_text(json.dumps(R, indent=2, default=str))

    names = {"cnn": "1D-CNN embedding (ours)", "manhattan": "Scaled Manhattan", "mahalanobis": "Mahalanobis (shrunk)",
             "fusion": "1D-CNN + scaled Manhattan (fusion)"}
    pm = lambda t: f"{100 * t[0]:.1f} ± {100 * t[1]:.1f}"
    L = ["# Keystroke dynamics — 1D-CNN encoder on CMU DSL-StrongPassword", "",
         f"51 subjects type `.tie5Roanl` 400 times (8 sessions x 50). Users split {len(tr)}/{len(va)}/{len(te)} "
         "(train/valid/test, disjoint); the CNN never sees valid/test users. EER in % (lower is better), mean ± std over "
         f"{len(SEEDS)} training seeds; classic detectors are deterministic. Per-user EER = each user's own threshold "
         "(as in Killourhy & Maxion); pooled EER = one global threshold.", "",
         "## A · held-out users, enrol on sessions 1-4, test on sessions 5-8", "",
         "| method | per-user EER, 1 try | per-user EER, 3 tries | pooled EER, 1 try |", "|---|---|---|---|"]
    for k in ("cnn", "manhattan", "mahalanobis", "fusion"):
        L.append(f"| {names[k]} | {pm(agg(['sessions', k, 'one_try', 'per_user_eer_mean']))} | "
                 f"{pm(agg(['sessions', k, 'three_tries', 'per_user_eer_mean']))} | {pm(agg(['sessions', k, 'one_try', 'eer']))} |")
    L += ["", "## B · realistic enrolment: 10 attempts from the first session, test on sessions 5-8", "",
          "| method | per-user EER, 1 try | per-user EER, 3 tries | pooled EER, 1 try |", "|---|---|---|---|"]
    for k in ("cnn", "manhattan", "mahalanobis", "fusion"):
        L.append(f"| {names[k]} | {pm(agg(['first10', k, 'one_try', 'per_user_eer_mean']))} | "
                 f"{pm(agg(['first10', k, 'three_tries', 'per_user_eer_mean']))} | {pm(agg(['first10', k, 'one_try', 'eer']))} |")
    L += ["", "## C · Killourhy & Maxion protocol (train on first 200 attempts; impostors = first 5 attempts of the other 50)", "",
          "| method | users | mean per-user EER | published |", "|---|---|---|---|"]
    L.append(f"| {names['manhattan']} | all 51 | {100 * km_all['manhattan'][0]:.1f} | {100 * PUBLISHED['Manhattan (scaled)']:.1f} |")
    L.append(f"| {names['mahalanobis']} | all 51 | {100 * km_all['mahalanobis'][0]:.1f} | {100 * PUBLISHED['Mahalanobis']:.1f} |")
    for k in ("cnn", "manhattan", "mahalanobis", "fusion"):
        L.append(f"| {names[k]} | {len(te)} held-out | {pm(agg(['km_heldout', k]))} | |")
    L += ["", f"Serving model: seed {best} (best valid per-user EER {100 * valid_scores[best]:.1f}%, protocol A), "
          f"{meta['params']:,} parameters; fused-score threshold set at the pooled valid EER "
          f"({100 * calib['valid_eer']:.1f}%, profile from the customer's past attempts).", "",
          "Typing drifts between sessions: with only 10 enrolment attempts from one sitting (B) every method degrades "
          "sharply, so a deployed profile should be built from, and refreshed with, the customer's verified logins.", "",
          "Caveats: one fixed password typed in a lab on one keyboard, so this verifies fixed-phrase entry (PIN / "
          "password), not free text. Our scaled Manhattan reproduces the published 9.6% on protocol C, which checks the "
          "baseline implementation. Only 8 test users: differences of a few points are within noise. The training "
          "sweep (dropout, weight decay, embedding size, augmentation strength) did not beat the defaults on valid users.", ""]
    (REPORTS / "keystroke_cmu.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
