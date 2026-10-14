# Robustness: adaptive scammers

Each row is a fresh simulated world (4,000 sessions, 20% scams, seed 101) never used in training, in which every scam session uses the tactic named (genuine sessions unchanged). Everything downstream is the shipped pipeline: honest payee scores, the real HMOG biometrics scorer, the workflow GRU, fusion at a 0.5% real-world prior and the full alert policy, replayed in time order. The tactics are our model of adaptation and the detectors never saw them: this measures graceful degradation under shift, not real adversaries.

| scenario | what the scammer changes | session AUC (GRU) | session AUC (fused) | scams interrupted in time | expected stopped in time | money saved | genuine interruptions / 1k |
|---|---|---|---|---|---|---|---|
| baseline (no adaptation) | nothing | 0.9998 | 0.9999 | 99.38% | 89.22% (+0.0) | 89.72% | 3.5 |
| no_call | calls move to an OTT app the bank can't see | 0.9746 | 0.9865 | 80.25% | 69.37% (-19.8) | 79.71% | 3.5 |
| slow | the workflow is stretched 5x in time | 0.9954 | 0.9959 | 93.88% | 83.36% (-5.9) | 87.74% | 3.8 |
| split_amounts | each payment split into 3-5 smaller ones | 0.9998 | 0.9998 | 97.5% | 87.04% (-2.2) | 89.72% | 1.3 |
| clean_device | no sideloaded app, no screen control or sharing | 0.9998 | 0.9998 | 98.75% | 88.07% (-1.2) | 89.73% | 3.5 |
| calm_hands | touch behaviour stays normal | 0.9995 | 0.9995 | 98.5% | 87.96% (-1.3) | 89.65% | 3.2 |
| fresh_numbers | calls from never-reported numbers | 0.9997 | 0.9998 | 99.0% | 88.62% (-0.6) | 89.52% | 3.5 |
| all tactics at once | everything above | 0.7832 | 0.9477 | 36.62% | 30.59% (-58.6) | 77.37% | 1.6 |

Largest drop from a single tactic: **no_call** (69.37% vs 89.22% stopped in time). With every tactic at once only 30.59% of scams are stopped in time, yet 77.37% of the money is still saved: the large payments that make up most of the loss still look anomalous. Genuine interruptions do not rise in any scenario, so adaptation costs detection, not extra false alarms.

## By scam difficulty (baseline world)

Difficulty is the simulator's per-scam knob (0 = textbook, 1 = hardest: weaker touch shifts, fewer VoIP calls, more dropped calls and store installs).

| difficulty | scam sessions | interrupted in time | expected stopped in time | money saved |
|---|---|---|---|---|
| 0.00-0.33 | 207 | 99.52% | 89.37% | 89.52% |
| 0.33-0.66 | 360 | 98.89% | 88.62% | 89.63% |
| 0.66-1.00 | 233 | 100.0% | 90.02% | 89.98% |
