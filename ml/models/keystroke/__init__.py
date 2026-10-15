"""Keystroke dynamics (CMU DSL-StrongPassword): 1D-CNN encoder over the 11 keystrokes of a fixed password.

    data.py      load the CMU CSV; the 31 timing columns in key order
    model.py     KeystrokeEncoder: raw timings -> per-key sequence -> 1D-CNN -> L2-normalised embedding
    train.py     CosFace training over train users, open-set EER on valid users
    evaluate.py  held-out users vs scaled-Manhattan / Mahalanobis baselines -> ml/reports/keystroke_cmu.md
    scorer.py    serving: enrol a user's typing, score a new attempt (CNN + scaled Manhattan, calibrated)
"""
