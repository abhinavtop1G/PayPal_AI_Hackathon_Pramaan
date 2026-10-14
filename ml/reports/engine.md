# Fusion + alert policy engine — simulator test period

> Simulator results (near-separable data, assumed tier efficacy/friction): they validate the engine's behaviour, not real-world accuracy. Payee intelligence and behavioural deviation are simulator stand-ins for the GNN and HMOG models.

## Fusion vs workflow GRU (1% benign false-alert budget, thresholds from valid)

| detector | PR-AUC | scams caught in time | FA: hospital_emergency | FA: bank_app_update | FA: legit_investing | FA: genuine_urgent_family |
|---|---|---|---|---|---|---|
| gru | 0.9958 | 99.8% | 0.0% | 0.0% | 16.4% | 1.6% |
| fused | 0.9913 | 99.8% | 0.0% | 0.3% | 10.9% | 12.7% |

Look-alike test sessions: hospital_emergency n=228, bank_app_update n=349, legit_investing n=274, genuine_urgent_family n=251 (one session moves a rate by 100/n points).

Note: the fused score is not uniformly better than the GRU alone (PR-AUC 0.9913 vs 0.9958; more false alerts on bank_app_update, genuine_urgent_family). The engine's gains below come from expected-value tiering on the fused, prior-corrected risk, not from a better ranking.

Monotone XGBoost fusion, gain importance: {'gru_logit': 1222.85, 'mule_score': 16.57, 'bio_dev': 5.0, 'log_amt_vs_avg': 3.95, 'payee_is_new': 1.98, 'unknown_call_active': 0.0, 'caller_reported_active': 1.74, 'payee_known_trusted': 0.0}

## Policy comparison (test replay)

Tiers (efficacy / friction in ₹-equivalent, assumptions): {'allow': {'efficacy': 0.0, 'friction': 0.0}, 'nudge': {'efficacy': 0.2, 'friction': 10.0}, 'cool_off': {'efficacy': 0.5, 'friction': 60.0}, 'hold': {'efficacy': 0.9, 'friction': 250.0}}. Real-world prior 0.5% of payment attempts. Only a new interruption carries its tier's efficacy (a payment that stays held in an already-held session is the same hold); repeat warnings without anti-fatigue are assumed independent, which flatters the no-anti-fatigue row. Holds = new holds per 1k benign sessions.

| policy | notifications / 1k benign sessions | holds / 1k benign | benign users interrupted | users interrupted 3+ times | scams expected stopped in time | expected money saved | interrupted: hospital_emergency | interrupted: bank_app_update | interrupted: legit_investing | interrupted: genuine_urgent_family |
|---|---|---|---|---|---|---|---|---|---|---|
| GRU threshold -> hold | 8.0 | 8.0 | 1.02% | 0.0% | 89.84% | 89.95% | 0.0% | 0.0% | 16.4% | 1.6% |
| Fused threshold -> hold | 10.6 | 10.6 | 1.36% | 0.0% | 89.79% | 89.95% | 0.0% | 0.3% | 10.9% | 12.7% |
| Engine (EV tiers, no anti-fatigue) | 1.1 | 0.3 | 0.14% | 0.0% | 91.16% | 96.76% | 0.0% | 0.0% | 0.0% | 2.8% |
| Engine (full) | 1.1 | 0.3 | 0.14% | 0.0% | 89.38% | 89.85% | 0.0% | 0.0% | 0.0% | 2.8% |

Anti-fatigue rules: benign interruptions per 1k sessions 1.1 -> 1.1; benign holds per 1k sessions 0.3 -> 0.3; scams expected stopped in time pct 91.16 -> 89.38; expected money saved pct 96.76 -> 89.85.

## Operating curve (full engine vs assumed real-world prior)

| assumed prior | notifications / 1k benign | holds / 1k benign | scams expected stopped in time | expected money saved | genuine_urgent_family interrupted |
|---|---|---|---|---|---|
| 0.1% | 0.3 | 0.2 | 89.02% | 89.74% | 0.8% |
| 0.2% | 0.3 | 0.3 | 89.25% | 89.82% | 0.8% |
| 0.5% | 1.1 | 0.3 | 89.38% | 89.85% | 2.8% |
| 1.0% | 2.7 | 0.3 | 89.54% | 89.93% | 6.4% |
| 2.0% | 5.8 | 0.3 | 89.68% | 90.02% | 13.9% |
| 5.0% | 10.4 | 1.1 | 89.76% | 90.08% | 24.3% |

## Example decisions (full engine)

Each example session is replayed alone with a fresh policy state, so per-user history from the full replay does not apply here.

| typology | t (min) | amount | stage | p (real prior) | action | why |
|---|---|---|---|---|---|---|
| digital_arrest | 14.1 | 21000 | extraction | 0.99888 | hold | session follows a known scam pattern; receiving account is linked to suspected mule activity; the number calling you has been reported for fraud |
| digital_arrest | 31.4 | 29554 | extraction | 0.99666 | hold | suppressed: session_on_hold |
| digital_arrest | 35.1 | 41000 | extraction | 0.99945 | hold | suppressed: session_on_hold |
| digital_arrest | 39.6 | 57925 | extraction | 0.99960 | hold | suppressed: session_on_hold |
| voice_clone_relative | 3.5 | 38000 | extraction | 0.99473 | hold | session follows a known scam pattern; receiving account is linked to suspected mule activity; touch behaviour differs from your usual pattern |
| genuine_urgent_family | 27.1 | 8000 | none | 0.00003 | allow |  |
| fake_kyc_apk | 17.1 | 34226 | extraction | 0.99979 | hold | session follows a known scam pattern; receiving account is linked to suspected mule activity; touch behaviour differs from your usual pattern |
| fake_kyc_apk | 17.5 | 41854 | extraction | 0.99971 | hold | suppressed: session_on_hold |
| fake_kyc_apk | 18.3 | 21541 | extraction | 0.99955 | hold | suppressed: session_on_hold |
| fake_kyc_apk | 18.9 | 42458 | extraction | 0.99942 | hold | suppressed: session_on_hold |
| fake_kyc_apk | 19.6 | 30676 | extraction | 0.99939 | hold | suppressed: session_on_hold |
| fake_kyc_apk | 20.1 | 43454 | extraction | 0.99955 | hold | suppressed: session_on_hold |

Example message (digital_arrest, hold):

- EN: This payment is on hold and your bank will call you on your registered number. Police, CBI or customs never ask you to transfer money or stay on a video call. This matches a 'digital arrest' scam. Hang up and call 1930.
- HI: यह भुगतान रोका गया है और आपका बैंक आपके रजिस्टर्ड नंबर पर कॉल करेगा। पुलिस, CBI या कस्टम कभी भी पैसे ट्रांसफ़र करने या वीडियो कॉल पर बने रहने को नहीं कहते। यह 'डिजिटल अरेस्ट' ठगी जैसा है। कॉल काटें और 1930 पर कॉल करें।
