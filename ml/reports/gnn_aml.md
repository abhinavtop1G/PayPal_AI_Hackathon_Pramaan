# IBM AML HI-Small — laundering transaction detection

Chronological 60/20/20 edge split (test = latest 20% of transactions, laundering rate 0.177% vs 0.075% in train). Each model sees only events strictly before the scored transaction. Threshold maximises valid minority-class F1; metrics below are on test (mean ± std over seeds).

| model | seeds | test F1 | precision | recall | PR-AUC | ROC-AUC | valid F1 |
|---|---|---|---|---|---|---|---|
| Temporal GNN, diff attention | 3 | 0.6957 ± 0.0026 | 0.7851 ± 0.0104 | 0.6247 ± 0.0084 | 0.6845 ± 0.0042 | 0.9877 ± 0.0013 | 0.6242 ± 0.0009 |
| Temporal GNN, vanilla attention | 3 | 0.7008 ± 0.0106 | 0.7958 ± 0.0237 | 0.6262 ± 0.0074 | 0.6897 ± 0.0105 | 0.9876 ± 0.0004 | 0.6319 ± 0.0080 |
| XGBoost + neighbourhood aggregates | 1 | 0.6105 | 0.7192 | 0.5303 | 0.6031 | 0.9851 | 0.5687 |

Learned differential-attention λ at the selected epoch: 0.5510 ± 0.1020.
