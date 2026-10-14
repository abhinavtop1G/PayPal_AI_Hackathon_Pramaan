# Payee side: v1 vs v2 features (emerging-pattern signals)

v2 adds four causal per-account features to `ml/campaign/features.py`:
- `amount_mode_share_24h`: share of 24 h credits at the 3 most common amounts (fixed-fee fronts);
- `amount_cv_24h`: spread of credit amounts (uniform = suspicious);
- `payback_share_24h`: debits sent back to accounts that paid this one in the last 72 h (fake payouts / commissions);
- `payer_multi_new_share_24h`: payers who also paid *another* account for the first time in the last 72 h (victims bounced
  between new accounts). This is the cross-account network signal used instead of wiring the IBM-AML GNN into the payee side.

Like-for-like comparison: the same simulator and ledger (10,000 sessions, seed 7, before per-session random streams were
introduced) and the same evaluation; only the feature set differs. `campaign_v1_baseline.json` is the v1 run.
The current `campaign.md` is the v2 model on the final generator, so its figures differ slightly from the v2 column here.

| slice (test period) | v1 ROC-AUC / PR-AUC / recall@1%FPR | v2 ROC-AUC / PR-AUC / recall@1%FPR |
|---|---|---|
| all credits | 0.8342 / 0.7611 / 0.6582 | 0.8356 / 0.7631 / 0.6640 |
| cold start (first credit) | 0.4749 / 0.3623 / 0.3333 | 0.4789 / 0.3692 / 0.3667 |
| excluding the novel campaigns | 0.9985 / 0.9930 / 0.9743 | 0.9986 / 0.9936 / 0.9774 |
| novel A: wrong-credit return scam | 0.9942 / 0.6546 / 0.8445 | **0.9978 / 0.8514 / 0.9399** |
| novel B: merchant-like micro-fee front | 0.4879 / 0.0911 / 0.0033 | 0.4918 / 0.0917 / 0.0062 |

| emerging-pattern radar | v1 | v2 |
|---|---|---|
| anomaly AUC vs benign, novel A / B | 0.918 / 0.908 | 0.888 / **0.981** |
| snapshots above the alert threshold, A / B | 13.3% / 5.2% | 36.6% / 50.9% |
| novel-campaign clusters confirmed in the test period | 0 | **5** |
| false clusters in the test period | 2 | 2 |
| novel B detected by the radar | no | **yes, 8 h after its first victim credit; 12 of 13 accounts** |

Reading: the supervised model still cannot learn a pattern it has never seen a label for (novel B stays at AUC 0.49), but
the new features give the unsupervised radar the shape signal it was missing, so the merchant-like front is now caught by
the radar while it is still young. Cold start remains unsolved on the payee side; the payer-side session engine covers it.
