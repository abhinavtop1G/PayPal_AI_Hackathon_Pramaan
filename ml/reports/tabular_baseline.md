# IEEE-CIS XGBoost baseline

Time-based split: train 413,378 / valid 59,053 / test 118,109 rows; test fraud rate 3.44%. False-alert cost c_fp = 10.0. Threshold chosen on valid, metrics on test.

| variant | roc_auc | pr_auc | recall_at_1pct_fpr | precision_at_thr | recall_at_thr | alerts_per_1k_txn | fraud_amt_caught_pct | cost_saved_vs_no_model_pct | brier |
|---|---|---|---|---|---|---|---|---|---|
| plain | 0.8893 | 0.4811 | 0.425 | 0.1851 | 0.7138 | 132.71 | 67.11 | 46.17 | 0.02357 |
| spw | 0.8904 | 0.4713 | 0.4095 | 0.1697 | 0.7372 | 149.44 | 71.43 | 47.4 | 0.02357 |
| cost | 0.887 | 0.4814 | 0.4132 | 0.152 | 0.7677 | 173.84 | 68.49 | 39.94 | 0.02369 |

## Top features by mean |SHAP| (plain variant)

1. `R_emaildomain` — 0.8123
2. `id_20` — 0.655
3. `C13` — 0.5965
4. `id_19` — 0.4849
5. `id_13` — 0.4321
6. `id_31` — 0.4314
7. `C1` — 0.3327
8. `card1` — 0.3109
9. `addr1` — 0.2795
10. `TransactionAmt` — 0.279
11. `card2` — 0.2742
12. `id_17` — 0.2586
13. `DeviceInfo` — 0.2502
14. `C14` — 0.2479
15. `P_emaildomain` — 0.235
16. `id_14` — 0.226
17. `card1_n_distinct_addr` — 0.2225
18. `id_33` — 0.2037
19. `C2` — 0.1974
20. `amt_log` — 0.1918
21. `id_30` — 0.1851
22. `D1` — 0.1833
23. `hour` — 0.1794
24. `D10` — 0.1788
25. `id_24` — 0.1714
