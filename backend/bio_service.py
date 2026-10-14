"""Behavioural biometrics service for the API: the shared scorer in ml/models/biometrics/scorer.py.

Score = BiLSTM + LDA score fusion (ml/reports/biometrics_hmog.md); see the scorer for calibration details.
"""
from ml.models.biometrics.scorer import BioScorer as BioService  # noqa: F401  (name kept for backend/app.py)
