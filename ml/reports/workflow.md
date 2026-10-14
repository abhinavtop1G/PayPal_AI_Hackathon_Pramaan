# Workflow sequence model — simulator sessions

50k simulated sessions (20% scams, incl. legitimate look-alikes of each scam workflow); split by session start: days 0–60 train, 60–75 valid, 75–90 test (voice-clone share of scams rises 17% → 29%). Alerts may only fire at payment attempts; *in time* = at or before the first extraction payment. Thresholds set on valid for a benign false-alert budget, applied unchanged to test.

> **Caveat:** the simulator is near-separable for scam-vs-benign (both models catch ≈99–100% of scams in time). These numbers validate the pipeline, not real-world accuracy. The informative comparisons are stage tracking and false alerts on look-alike sessions.

## Stage tracking and typology

| model | stage macro-F1 (scam sessions) | stage accuracy | typology acc. at first extraction | payment-attempt PR-AUC |
|---|---|---|---|---|
| Workflow GRU (3 seeds) | 0.883 ± 0.004 | 0.963 ± 0.002 | 0.995 ± 0.000 | 0.995 ± 0.001 |
| XGBoost bag-of-events (1 seed) | 0.815 | 0.931 | 0.995 | 0.991 |

## Alerting at a 1% benign false-alert budget

| model | benign FA rate | scams caught in time | money saved % | FA: hospital_emergency | FA: bank_app_update | FA: legit_investing | FA: genuine_urgent_family |
|---|---|---|---|---|---|---|---|
| Workflow GRU | 0.9 ± 0.1% | 99.6 ± 0.1% | 99.7 ± 0.1% | 0.0 ± 0.0% | 0.0 ± 0.0% | 17.3 ± 3.3% | 4.2 ± 1.7% |
| XGBoost bag-of-events | 1.0% | 99.7% | 99.9% | 0.0% | 0.9% | 16.7% | 6.8% |

## Alerting at a 5% benign false-alert budget

| model | benign FA rate | scams caught in time | money saved % | FA: hospital_emergency | FA: bank_app_update | FA: legit_investing | FA: genuine_urgent_family |
|---|---|---|---|---|---|---|---|
| Workflow GRU | 4.9 ± 0.1% | 99.9 ± 0.0% | 100.0 ± 0.0% | 0.7 ± 0.2% | 3.7 ± 1.8% | 34.3 ± 3.4% | 73.9 ± 2.8% |
| XGBoost bag-of-events | 4.3% | 100.0% | 100.0% | 0.8% | 7.6% | 43.3% | 31.7% |

Naive rule (unknown caller + new payee): benign FA 15.9%, scams caught in time 54.8% (misses all fake-KYC and investment scams: {'digital_arrest': 0.84, 'fake_kyc_apk': 0.0, 'investment_task': 0.0, 'voice_clone_relative': 1.0}).
