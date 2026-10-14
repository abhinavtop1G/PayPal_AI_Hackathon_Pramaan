"""Payee-side campaign intelligence: what the *receiving* side of UPI can see.

    ledger     synthetic transfer ledger (scam money trails, benign look-alikes, one held-out novel scam)
    features   causal point-in-time account features (no future information, same code for training and serving)
    payee_model  XGBoost payee-risk model with reason codes
    campaigns  online tracker that links risky accounts into campaigns and ranks cases by recoverable rupees
    radar      unsupervised emerging-pattern detector for campaigns the supervised model has never seen
    evaluate   end-to-end report -> ml/reports/campaign.md
"""
