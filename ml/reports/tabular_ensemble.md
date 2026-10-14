# IEEE-CIS ensemble (CatBoost + LightGBM + XGBoost)

Time-based split, metrics on the time-later test slice (118,109 rows). c_fp = 10.0; thresholds chosen on valid. Base models: xgb (best iter 1133, 66s), lgb (best iter 208, 61s), cat (best iter 1686, 325s).

PP: `none` raw scores | `causal` client's running mean (deployable) | `full` client's mean incl. future transactions (Kaggle-style, **leaky upper bound**).

| model | pp | ROC-AUC | PR-AUC | recall@1%FPR | alerts/1k | cost saved % |
|---|---|---|---|---|---|---|
| stack_lr(cat+lgb+xgb) | causal | 0.9132 | 0.5085 | 0.4065 | 138.31 | 58.17 |
| lgb | causal | 0.9109 | 0.4966 | 0.3944 | 115.9 | 59.61 |
| mean(cat+lgb+xgb) | causal | 0.9109 | 0.5019 | 0.4065 | 133.33 | 57.74 |
| rank_mean(cat+lgb+xgb) | causal | 0.899 | 0.4682 | 0.3684 | 126.41 | 53.74 |
| cat | causal | 0.8979 | 0.4891 | 0.3974 | 139.45 | 54.93 |
| xgb | causal | 0.8967 | 0.4619 | 0.3652 | 147.8 | 47.31 |
| stack_lr(cat+lgb+xgb) | full | 0.9156 | 0.4976 | 0.388 | 127.66 | 58.09 |
| mean(cat+lgb+xgb) | full | 0.914 | 0.4919 | 0.3895 | 117.14 | 57.21 |
| lgb | full | 0.9139 | 0.4851 | 0.3706 | 119.47 | 58.25 |
| cat | full | 0.9011 | 0.4832 | 0.3802 | 109.23 | 55.36 |
| xgb | full | 0.8996 | 0.4537 | 0.3468 | 151.48 | 48.3 |
| rank_mean(cat+lgb+xgb) | full | 0.8994 | 0.4555 | 0.3521 | 105.99 | 53.56 |
| stack_lr(cat+lgb+xgb) | none | 0.9169 | 0.5535 | 0.4609 | 90.05 | 59.87 |
| mean(cat+lgb+xgb) | none | 0.915 | 0.5521 | 0.4621 | 97.33 | 59.15 |
| rank_mean(cat+lgb+xgb) | none | 0.9141 | 0.5486 | 0.4604 | 110.64 | 58.87 |
| lgb | none | 0.914 | 0.5418 | 0.4449 | 85.22 | 60.12 |
| xgb | none | 0.8994 | 0.5134 | 0.4333 | 135.32 | 49.02 |
| cat | none | 0.8957 | 0.527 | 0.4508 | 113.81 | 55.71 |
