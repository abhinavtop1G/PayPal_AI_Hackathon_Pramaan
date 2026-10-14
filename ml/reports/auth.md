# Transaction authentication (BIOS) — allow / challenge / block on the account-takeover simulator

> Simulated customers and attacks (ml/auth/sim.py); touch windows are real HMOG gestures scored by the real BiLSTM + LDA model; challenge efficacies and genuine pass rates are **assumptions** (ml/auth/policy.py). The numbers validate the service and compare designs; they are not real-world accuracy.

Traffic: 3,000 customers, 273,053 requests over 60 days (1,679 attack requests); touch scores: hmog. Train days 0-35, valid 35-45, test 45-60 replayed through the service. Assumed real-world attack prevalence: 0.2% of requests (simulator: 0.65%).

## Ranking quality (test requests, full model)

| model | ROC-AUC | PR-AUC |
|---|---|---|
| risk engine (all signals) | 0.9974 | 0.8901 |
| behaviour signals only | 0.7954 | 0.1556 |
| device signals only | 0.7624 | 0.4914 |
| transaction signals only | 0.9533 | 0.5455 |

Family-only models are trained on the same rows with only that family's features (ablation).

## Decisions on the test period (replayed through the service)

| design | genuine challenged | genuine blocked (final) | attack requests stopped | attack money stopped | attack campaigns with any success |
|---|---|---|---|---|---|
| risk engine (all signals) | 1.99% | 0.092% | 85.8% | 87.37% | 23.39% |
| behaviour signals only | 3.9% | 0.141% | 62.84% | 65.24% | 47.58% |
| device signals only | 0.69% | 0.035% | 50.15% | 51.38% | 56.45% |
| transaction signals only | 4.81% | 0.229% | 76.44% | 79.4% | 29.03% |
| SMS OTP on every payment | 100.0% | 2.996% | 24.17% | 24.03% | 93.55% |
| rules engine + SMS OTP | 3.71% | 0.123% | 30.21% | 31.05% | 81.45% |

## Per scenario, risk engine (first decision; final = after the challenge)

| scenario | requests | allow | challenge | block | finally blocked |
|---|---|---|---|---|---|
| genuine | 68164 | 98.0% | 2.0% | 0.0% | 0.1% |
| routine | 60285 | 99.8% | 0.2% | 0.0% | 0.0% |
| new_phone | 631 | 91.6% | 8.4% | 0.0% | 0.5% |
| travel | 441 | 99.3% | 0.7% | 0.0% | 0.0% |
| big_purchase | 1933 | 42.5% | 57.5% | 0.1% | 2.3% |
| web | 4874 | 98.5% | 1.5% | 0.0% | 0.1% |
| ato_new_device | 75 | 0.0% | 12.0% | 88.0% | 100.0% |
| sim_swap | 63 | 0.0% | 15.9% | 84.1% | 100.0% |
| bot | 29 | 0.0% | 48.3% | 51.7% | 100.0% |
| remote_access | 71 | 2.8% | 25.4% | 71.8% | 87.3% |
| coerced | 93 | 18.3% | 43.0% | 38.7% | 59.1% |

Challenge mix (risk engine): {'sms_otp': 1108, 'bank_callback': 245, 'passkey': 96}

## Attacks by difficulty (risk engine)

| difficulty | attack requests | stopped |
|---|---|---|
| easy (0-0.33) | 113 | 92.0% |
| medium | 100 | 94.0% |
| hard (0.66-1) | 118 | 72.9% |

## Latency

in-process: features + model + SHAP + policy + state, CPU, memory state; excludes touch scoring and HTTP: p50 8.49 ms, p95 13.27 ms, p99 39.11 ms over 2000 requests.

## Most important features (gain)

| feature | family | gain |
|---|---|---|
| geo_speed | device | 278.0 |
| device_new | device | 163.8 |
| remote_access_app | device | 90.5 |
| new_city | device | 86.1 |
| amt_z | transaction | 66.0 |
| hour_rarity | transaction | 44.5 |
| unknown_call_active | behaviour | 42.1 |
| accounts_on_device | device | 38.7 |
| payee_risk | transaction | 36.6 |
| low_input | behaviour | 29.3 |
| payee_new | transaction | 28.4 |
| fast_submit | behaviour | 27.4 |
| screen_share_active | behaviour | 22.4 |
| n_devices_30d | device | 22.1 |
| emulator | device | 21.4 |

## Assumptions

P(challenge stops the attack):

| challenge | ato_new_device | sim_swap | bot | remote_access | coerced | genuine pass |
|---|---|---|---|---|---|---|
| sms_otp | 0.50 | 0.00 | 0.90 | 0.20 | 0.05 | 0.97 |
| passkey | 0.95 | 0.95 | 0.99 | 0.40 | 0.10 | 0.98 |
| bank_callback | 0.90 | 0.30 | 0.99 | 0.85 | 0.60 | 0.90 |
| cool_off | 0.60 | 0.50 | 0.90 | 0.60 | 0.50 | 0.85 |

Policy costs (rupee-equivalents): {"friction": {"sms_otp": 8.0, "passkey": 6.0, "bank_callback": 60.0, "cool_off": 40.0}, "block_cost": 400.0, "login_exposure": 20000.0, "block_min_p": 0.5}
