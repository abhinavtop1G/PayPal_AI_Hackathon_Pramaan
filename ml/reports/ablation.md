# Ablation: what the real biometrics model and the telecom signal add

Same GRU scores, same simulated test period, same alert policy (full, 0.5% real-world prior); fusion refitted per variant on the same rows. Simulator data: the signals' effect depends on our assumptions about how often scam numbers are already reported and how often fraud happens on someone else's hands (overlay / remote-control apps).

| variant | payment PR-AUC | fake-KYC vs bank-update PR-AUC | scams stopped in time | money saved | genuine interruptions / 1k | genuine holds / 1k | fusion gain: touch / caller reported |
|---|---|---|---|---|---|---|---|
| full | 0.9999 | 1.0 | 89.38% | 89.85% | 1.1 | 0.3 | 5.0 / 1.74 |
| stand-in biometrics | 0.9999 | 1.0 | 89.57% | 89.89% | 1.1 | 0.3 | 3.0 / 3.15 |
| no touch signal | 0.9999 | 1.0 | 89.36% | 89.86% | 0.9 | 0.3 | 0.0 / 3.74 |
| no telecom signal | 0.9999 | 1.0 | 89.38% | 89.85% | 1.1 | 0.3 | 4.83 / 0.0 |

Look-alike sessions interrupted (%): **full** {'hospital_emergency': np.float64(0.0), 'bank_app_update': np.float64(0.0), 'legit_investing': np.float64(0.0), 'genuine_urgent_family': np.float64(2.8)}; **stand-in biometrics** {'hospital_emergency': np.float64(0.0), 'bank_app_update': np.float64(0.0), 'legit_investing': np.float64(0.0), 'genuine_urgent_family': np.float64(2.8)}; **no touch signal** {'hospital_emergency': np.float64(0.0), 'bank_app_update': np.float64(0.0), 'legit_investing': np.float64(0.0), 'genuine_urgent_family': np.float64(2.4)}; **no telecom signal** {'hospital_emergency': np.float64(0.0), 'bank_app_update': np.float64(0.0), 'legit_investing': np.float64(0.0), 'genuine_urgent_family': np.float64(2.8)}
