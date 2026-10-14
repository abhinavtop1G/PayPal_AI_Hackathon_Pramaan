# Architecture: risk-based transaction authentication (BIOS)

> Problem: *build a cloud authentication service that uses behaviour, device information and transaction patterns to
> allow, challenge or block an online transaction, and returns a decision with the signals behind it, in real time.*
> The scam-session and payee-side layers this builds on (RAKSHAM) are described in `ARCHITECTURE_RAKSHAM.md`.

## Request path

```
 client SDK ──► gateway (API key · HMAC signature · replay check · rate limit)            POST /v1/authenticate
                  │
                  ▼
 enrich ── touch: 10–20 gestures → BiLSTM + LDA verifier vs the user's enrolled profile → bio_dev
       └── payee: payee-risk model (payee-side layer) if the receiving account is known → payee_risk
                  │
                  ▼
 features (26, causal, ml/auth/features.py) ◄── live state (Redis / memory): user history, device registry,
   behaviour 5 · device 13 · transaction 8         per-device and per-IP account fan-out, failed challenges
                  │
                  ▼
 monotone XGBoost → risk (prior-corrected) ─► tree-SHAP: per-signal + per-family contributions
                  │
                  ▼
 policy: choose the step-up that fits the signals, then expected cost of allow / challenge / block
                  │
                  ▼
 { decision, risk_score, challenge_type, reasons (EN/HI), signals, latency_ms }  ──► audit log (Postgres / SQLite)
                  │ challenge
                  ▼
 POST /v1/challenge/verify ── passed: commit to history, trust device (passkey / call-back) · failed: block 30 min
```

## Components

| component | module | status |
|---|---|---|
| IP intelligence, geo header | `ml/auth/geo.py` | built (demo provider / Tor ranges; production needs a maintained feed) |
| live state | `ml/auth/state.py` | built: in-memory and Redis backends |
| features | `ml/auth/features.py` | built, tested for causality (reads only state written before the request) |
| account-takeover simulator | `ml/auth/sim.py` | built: genuine look-alikes + 5 attack types with a difficulty knob; real HMOG touch windows |
| risk model | `ml/auth/model.py` | built: monotone XGBoost, prior correction, exact tree-SHAP |
| policy | `ml/auth/policy.py` | built: signal-matched challenge, expected-cost decision, escalation, hard rules |
| service | `ml/auth/engine.py`, `backend/auth_service.py` | built: decision + challenge loop + audit |
| touch biometrics | `ml/models/biometrics` | built earlier (HMOG, EER 14.4%); calibration shipped so containers need no dataset |
| payee intelligence | `ml/campaign` | built earlier; used when the receiving account is known |
| security | `backend/security.py` | built: API keys, HMAC + replay, token-bucket rate limit |
| audit | `backend/audit.py` | built: async writer, Postgres or SQLite, in-memory feed |
| cloud | `Dockerfile`, `docker-compose.yml`, `deploy/cloudrun.sh` | written; **not yet run** (no Docker / gcloud on the dev machine) |
| console | `frontend/` (`/`) | built: scenarios, custom builder, decision + challenge loop, SHAP signals, audit feed |
| client SDK | — | not built: the console stands in for it; signals the SDK would send are documented in `AuthRequest` |

## Decisions and why

* **One model over all three signal families, not three scores averaged.** Signals interact: a new device is normal
  after a SIM change only if the touch pattern still matches; a large amount is normal on a trusted device. The
  ablation in `ml/reports/auth.md` shows no single family comes close to the combination.
* **Monotone constraints.** Every feature can only raise risk. An attacker cannot lower the score by triggering a
  "risky" signal, and every explanation points the right way.
* **The challenge fits the signals.** An SMS OTP is useless after a SIM swap (the OTP goes to the attacker) and useless
  against a coached victim (the real owner types it). So: SIM change or new device → passkey on the registered device;
  remote-access app / someone else's hands → bank call-back; coaching on the owner's own device → cool-off with a scam
  warning; otherwise an OTP.
* **Block only when an attack is more likely than not.** Below 50% a large amount escalates to a stronger challenge
  instead, so a genuine big purchase is verified, not refused.
* **History is written only by completed transactions.** A blocked attacker never becomes part of the victim's normal;
  a device becomes trusted after 7 days and 3 completed payments, or after a strong challenge.
* **Missing data is information, not an error.** Web requests have no touch data, payee intelligence knows only some
  accounts, the first request has no location history; the model learns those cases (XGBoost default branches).

## Privacy and safety

* Raw touch data never leaves the device as raw coordinates: the SDK sends per-gesture features; profiles are
  embeddings. Identifiers are opaque; hash with a keyed HMAC before sharing across institutions.
* Consent gate (`infra/privacy/consent.py`, DPDP purposes) is available for behavioural biometrics and telecom data.
* Every decision is logged with its reasons, model version and latency for audit and dispute handling (RBI directions
  require issuers to compensate customers when authentication fails them).

## Known gaps

1. The attack and genuine behaviours are simulated; only the touch windows are real data. Challenge efficacies are
   assumptions. A bank pilot with labelled fraud is needed for real accuracy.
2. No public dataset joins behaviour, device and transaction signals for the same users.
3. IP ranges are a demo subset; production needs a maintained IP-intelligence feed and the SDK's device attestation
   (Play Integrity / App Attest) instead of client-reported emulator / root flags.
4. The cloud deployment files have not been run yet.
