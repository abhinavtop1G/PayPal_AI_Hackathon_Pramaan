# Transaction authentication (PRAMAAN) — allow / challenge / block on the account-takeover simulator

> Simulated customers and attacks (ml/auth/sim.py); touch windows are real HMOG gestures scored by the real BiLSTM + LDA model; challenge efficacies and genuine pass rates are **assumptions** (ml/auth/policy.py). The numbers validate the service and compare designs; they are not real-world accuracy.

Traffic: 3,000 customers, 273,053 requests over 60 days (1,679 attack requests); touch scores: hmog; typing scores: cmu (CMU keystroke attempts of held-out subjects, scored by the 1D-CNN + scaled Manhattan). Train days 0-35, valid 35-45, test 45-60 replayed through the service. Assumed real-world attack prevalence: 0.2% of requests (simulator: 0.65%).

## Ranking quality (test requests, full model)

| model | ROC-AUC | PR-AUC |
|---|---|---|
| risk engine (all signals) | 0.9964 | 0.8892 |
| behaviour signals only | 0.8802 | 0.2302 |
| device signals only | 0.7624 | 0.4914 |
| transaction signals only | 0.9533 | 0.5455 |

Family-only models are trained on the same rows with only that family's features (ablation).

## Decisions on the test period (replayed through the service)

| design | genuine challenged | genuine blocked (final) | attack requests stopped | attack money stopped | attack campaigns with any success |
|---|---|---|---|---|---|
| risk engine (all signals) | 1.81% | 0.082% | 82.78% | 83.37% | 25.81% |
| behaviour signals only | 1.99% | 0.097% | 71.9% | 79.01% | 42.74% |
| device signals only | 0.69% | 0.035% | 50.15% | 51.38% | 56.45% |
| transaction signals only | 4.81% | 0.229% | 76.44% | 79.4% | 29.03% |
| SMS OTP on every payment | 100.0% | 2.996% | 24.17% | 24.03% | 93.55% |
| rules engine + SMS OTP | 3.71% | 0.123% | 30.21% | 31.05% | 81.45% |

## Per scenario, risk engine (first decision; final = after the challenge)

| scenario | requests | allow | challenge | block | finally blocked |
|---|---|---|---|---|---|
| genuine | 68164 | 98.2% | 1.8% | 0.0% | 0.1% |
| routine | 60285 | 99.8% | 0.2% | 0.0% | 0.0% |
| new_phone | 631 | 91.4% | 8.6% | 0.0% | 0.5% |
| travel | 441 | 99.5% | 0.5% | 0.0% | 0.0% |
| big_purchase | 1933 | 48.8% | 51.1% | 0.1% | 2.1% |
| web | 4874 | 98.4% | 1.6% | 0.0% | 0.1% |
| ato_new_device | 75 | 0.0% | 6.7% | 93.3% | 100.0% |
| sim_swap | 63 | 0.0% | 11.1% | 88.9% | 100.0% |
| bot | 29 | 0.0% | 37.9% | 62.1% | 100.0% |
| remote_access | 71 | 5.6% | 19.7% | 74.6% | 90.1% |
| coerced | 93 | 23.7% | 40.9% | 35.5% | 46.2% |

Challenge mix (risk engine): {'sms_otp': 1001, 'bank_callback': 222, 'passkey': 87}

## Attacks by difficulty (risk engine)

| difficulty | attack requests | stopped |
|---|---|---|
| easy (0-0.33) | 113 | 95.6% |
| medium | 100 | 86.0% |
| hard (0.66-1) | 118 | 67.8% |

## Latency

in-process: features + model + SHAP + policy + state, CPU, memory state; excludes touch scoring and HTTP: p50 12.37 ms, p95 17.64 ms, p99 19.34 ms over 2000 requests.

## Most important features (gain)

| feature | family | gain |
|---|---|---|
| geo_speed | device | 223.1 |
| device_new | device | 156.9 |
| remote_access_app | device | 91.6 |
| amt_z | transaction | 58.0 |
| n_devices_30d | device | 56.1 |
| typing_dev | behaviour | 55.0 |
| hour_rarity | transaction | 37.3 |
| payee_risk | transaction | 36.0 |
| unknown_call_active | behaviour | 32.4 |
| payee_new | transaction | 27.2 |
| bio_dev | behaviour | 21.3 |
| screen_share_active | behaviour | 16.6 |
| accounts_on_device | device | 15.5 |
| new_city | device | 12.6 |
| fast_submit | behaviour | 12.4 |

## Assumptions

P(challenge stops the attack):

| challenge | ato_new_device | sim_swap | bot | remote_access | coerced | genuine pass |
|---|---|---|---|---|---|---|
| sms_otp | 0.50 | 0.00 | 0.90 | 0.20 | 0.05 | 0.97 |
| passkey | 0.95 | 0.95 | 0.99 | 0.40 | 0.10 | 0.98 |
| bank_callback | 0.90 | 0.30 | 0.99 | 0.85 | 0.60 | 0.90 |
| cool_off | 0.60 | 0.50 | 0.90 | 0.60 | 0.50 | 0.85 |

Policy costs (rupee-equivalents): {"friction": {"sms_otp": 8.0, "passkey": 6.0, "bank_callback": 60.0, "cool_off": 40.0}, "block_cost": 400.0, "login_exposure": 20000.0, "block_min_p": 0.5}
