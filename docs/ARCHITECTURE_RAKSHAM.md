# Architecture: one payee score, two halves of a scam

## The problem the design answers

A coached victim pays a mule account in seconds, and the mule forwards the money within minutes. Nobody holds the
whole picture:

* the **payer's app** knows the victim is on a long call with an unknown number, has screen-share open and is paying a
  new payee — but nothing about the account receiving the money;
* the **beneficiary side** knows that account is new, collects money from strangers and forwards it within minutes —
  but nothing about the phone call that caused each payment.

RAKSHAM runs one engine on each side and connects them through the payee-risk score.

## System

```
 PAYER SIDE (bank / PSP app)                                 PAYEE SIDE (beneficiary bank / switch)
 ───────────────────────────                                 ─────────────────────────────────────
 session events: call, screen-share,                         transfers: payer, payee, amount, time, bank
 sideload, SMS link, touch, amount                                      │
        │                                                               ▼
        ▼                                                     FeatureEngine (causal, per account)
 context tracker ──► workflow GRU ─┐                                    │
                                   ├─► fusion (monotone XGB)            ├─► payee-risk model (XGBoost, calibrated)
        payee risk ◄───────────────┼───────────────────────────────────┤        │ reason codes
   POST /v1/payee/score            │                                   │        ▼
                                   ▼                          CampaignTracker: taint along forwarded money,
                          alert policy (EV tiers,               links, corroboration gate, recoverable ₹
                          anti-fatigue, campaign floor)                 │
                                   │                                    ▼
                  allow / nudge / cool-off / hold            ranked cases ─► analyst: hold credits (human), report 1930
                  EN + HI message                            EN/HI case summary, recommended actions
```

## Components

| component | module | input | output | status |
|---|---|---|---|---|
| session simulator | `ml/sim` | — | scam workflows and benign look-alikes; mules in syndicates | built, tested |
| payee-side ledger | `ml/campaign/ledger.py` | simulator output | transfers: scam trails, forwarding chains, benign merchants / payroll / marketplaces / friends, two held-out novel scams | built, tested (synthetic) |
| causal features | `ml/campaign/features.py` | transfers | 28 per-account features (incl. fixed-amount share, amount spread, payouts back to payers, payers bounced between new accounts); same code for training and serving | built, tested for causality |
| payee-risk model | `ml/campaign/payee_model.py` | features | calibrated risk + reason codes | built; out-of-fold scores for training rows |
| campaign tracker | `ml/campaign/campaigns.py` | scored transfers | campaigns, cases ranked by recoverable ₹ | built, tested |
| emerging-pattern radar | `ml/campaign/radar.py` | account snapshots | clusters of anomalous, unexplained accounts | built; catches the merchant-like novel campaign since the v2 features (see below) |
| case narrative | `ml/campaign/narrative.py` | a case | EN/HI summary from numbers, no free text | built |
| workflow GRU, fusion, policy | `ml/models/workflow`, `ml/engine` | session events | stage, typology, alert tier | built; re-trained on the honest payee score, real touch scores and caller reputation |
| real touch biometrics | `ml/sim/hmog_bank.py`, `ml/models/biometrics/scorer.py` | 10 real HMOG gestures per touch window | deviation from the customer's enrolled profile | built; the same scorer serves the API and training data |
| caller reputation + consent | `infra/privacy/{psi,reputation,consent}.py` | caller number, consent artefact | "number reported to 1930" bit, learned by DH private set intersection, only with consent | built (teaching-grade crypto, demo telecom list) |
| robustness evaluation | `ml/engine/robustness.py` | adaptive-scammer worlds | detection under each tactic | built (`ml/reports/robustness.md`) |
| temporal GNN (IBM AML) | `ml/models/gnn` | IBM-AML transfers | laundering probability per transfer | built, served at `/v1/gnn/score`; **standalone** (its currency / payment-format inputs don't exist in UPI sessions; the payee model's network features cover the session path) |
| API | `backend/` | — | session, payee, campaign endpoints | built, tested (campaign); session path needs trained models |
| demo app (phone mock + analyst console) | `frontend/` | `POST /v1/demo/{typology}` (live or recorded) | session replay: risk timeline, reasons, policy costs, EN/HI hold alert | built (payer-side scenarios) |
| payee-side case UI | `frontend/` (Mule network view) | `/v1/campaign/cases`, `…/graph` | ranked cases, money-flow graph, EN/HI summaries, credit hold | built |
| on-device signal SDK, bank integration | — | — | — | **not built** |

## Decisions and why

* **One flagged account is not a case.** A case needs two linked flagged accounts, or one account flagged on three
  separate credits, *and* at least three distinct outside payers. Isolated false flags are usually one-offs, and a group
  of accounts that only pay each other (a friend group) is not a scam campaign.
* **Links come from money, not coincidence.** Taint flows along forwarded money. Linking accounts because the same payer
  paid both is off by default: over 90 days, coincidences between heavy-hitter accounts merged unrelated campaigns.
* **Holds are human, transaction-level, logged.** The service never freezes anything by itself. A named analyst applies a
  hold; the payer side then treats that payee as at least `cool_off`.
* **The payer-side rule uses campaign evidence only together with a risky session.** A flagged payee alone changes
  nothing; membership in a campaign raises a calm decision to `nudge` only if the session itself already scores ≥ 2%.
* **Labels are time-varying.** A mule account is positive from its first scam-related credit; its earlier ordinary credits
  are negatives. Otherwise the model wins by recognising the account instead of the behaviour.
* **Account age is capped at one year and lifetime counters are not model inputs.** Exact ages let the model memorise
  accounts, and lifetime counters grow with elapsed time. Both flattered validation scores until we looked at
  out-of-fold false flags.
* **Thresholds are set per account type on honest scores** (out-of-fold training rows plus validation), so busy merchants
  are not hidden behind thousands of quiet personal accounts.

## What the evidence says (`ml/reports/campaign.md`, synthetic ledger, 10k sessions; v2 features)

* Campaign tracking (2% benign budget): 21 cases, 19 containing mules (purity 100%), **2 cases with no mule and 2 benign
  accounts swept in** (v1 had none: the new features flag a few more benign accounts); 95.1% of mule accounts that received
  money end up in a case. Five syndicates are split over two or three cases.
* Recovery: with case-driven action 88.7% of scam credit value arrives after the receiving account is acted on, against
  82.8% under a complaint-driven baseline (assumed 24 h lag). The gap is modest because mule accounts live long and the
  first victims cannot be protected.
* **Cold start is not solved.** A brand-new account's first credit is scored at ROC-AUC 0.46 from the payee side alone.
  That is exactly why the payer-side session engine exists: it sees the victim.
* The first case opens a median 24.9 h after a syndicate's first victim credit (a case needs three distinct payers). The
  account-level flag comes earlier (median 3.6 h). Payer-side protection should use the flag; the case is for the analyst.
* **Novel scams (never in training).** Variant A (debit-heavy "wrong credit, return it") is caught by the supervised model
  (AUC 0.99, 12 of 13 accounts flagged). Variant B (a micro-fee front that looks like a small merchant) is invisible to the
  supervised model (AUC 0.47: no labelled example of that shape) but is now **caught by the radar**: 12 of 13 accounts in
  confirmed clusters 28 h after its first victim, with 89.6% of the value still arriving after action. The v1 radar missed
  both campaigns; the fix was the v2 features (fixed-amount share, payouts back to payers, payers bounced between new
  accounts), which lift its anomaly AUC on B from 0.91 to 0.98. Two false clusters (marketplace cohorts) remain, at the
  budget of at most two in the 15-day validation period.

## What the evidence says, payer side (`ml/reports/engine.md`, `ablation.md`, `robustness.md`)

* Engine (simulated test period, 0.5% real-world prior): 1.1 messages and 0.3 holds per 1,000 genuine sessions (v1: 2.8 and
  0.8) at the same scam stopping (89.4% stopped in time, 89.9% of money saved). Look-alike genuine sessions interrupted:
  0% except genuine urgent family transfers (2.8%, v1 6.1%).
* **Touch biometrics are now real.** Each customer is a held-out HMOG subject; the BiLSTM+LDA scorer flags 76% of windows
  made by someone else's hands against 25.5% of the owner's own, and 26% of "coerced" own-hand windows
  (`ml/reports/biometrics_in_sessions.md`, 111k windows): the model
  recognises *who* is touching, not *how stressed* they are, so it guards against overlay / remote-control fraud, and
  coercion stays the stage tracker's job.
* **Ablation honesty.** Swapping either new signal out of the fusion model changes almost nothing on ordinary simulated
  scams (all variants stop ~89.4%), because the retrained GRU already reads both and is near-perfect at payment time there.
* **Adaptive scammers** (fresh worlds, every scam using the tactic): single tactics cost 0.6–5.9 points of scams stopped in
  time, except moving the call to an app the bank can't see (89.2% → 69.4%). All tactics at once cut it to 30.6%, yet 77%
  of the money is still saved; genuine interruptions do not rise in any scenario.

## Privacy and safety

* The payee side uses only what a beneficiary bank already sees: its own account's credits and debits, payer ids, amounts,
  times, originating bank, account age. No message content, call audio, contacts or location.
* Payer-side raw SMS / call data would stay on the device and reach the server only as flags; that SDK does not exist yet.
* **Consent before signals** (`infra/privacy/consent.py`): every session carries a DPDP-style consent artefact
  (fraud_prevention, telecom_reputation, behavioural_biometrics). The caller check and the touch score run only if their
  purpose is consented; every check is written to an audit log.
* **Caller reputation without sharing lists** (`infra/privacy/psi.py`, `reputation.py`): the bank learns whether the number
  calling its customer is on the telecom's 1930-reported list by Diffie-Hellman private set intersection over a 2048-bit
  group; the telecom never sees the bank's numbers and the bank never sees the telecom's list. Teaching-grade (semi-honest,
  Python ints); production would use an audited library.
* Account ids are opaque; hash with a keyed HMAC before sharing across institutions. All processing is meant to run
  inside the bank's perimeter in India (payment-data localisation).
* Alerts explain themselves: reason codes come from tree-SHAP contributions on the risky side of the benign median, and
  the case summary is assembled from computed numbers, so every sentence can be checked against the case card.

## Known gaps

1. Everything is synthetic; the behaviours of mules, merchants and novel scams are our assumptions.
2. The session GRU and fusion are re-trained on the honest payee score, real touch scores and caller reputation; served
   scores match offline scores (parity test) and the suite has 90 tests. Coercion is modelled, not measured (HMOG has no
   coercion labels); the telecom's reported list and the share of scam numbers already on it (45%) are assumptions.
3. The temporal GNN is validated on real IBM-AML data but stays standalone; wiring it into decisions would mean retraining
   it on UPI-like traffic.
4. Hindi strings need review by a native speaker.
5. Cross-bank sharing (hashed campaign ids) is designed but not implemented; a single bank sees only its own side.
