# RAKSHAM — AI-driven scam recognition for UPI (PS-02)

Two layers that see different halves of the same scam, joined at one number — **the risk of the payee**:

| layer | where it runs | sees | decides |
|---|---|---|---|
| **Payer side** — session engine | inside the payer's bank / PSP app | call state, screen-share, sideloaded apps, SMS links, touch behaviour, amount, payee | one explained alert at the payment attempt: allow / nudge / cool-off / hold |
| **Payee side** — campaign engine | the beneficiary bank / UPI switch | credits and debits of receiving accounts: fan-in, pass-through, age, who paid, where money went | which accounts form a scam campaign, and a rupee-ranked case for the fraud team |

The payee side gives the payer side a real payee-risk score (replacing a simulator stand-in) and tells the fraud
team which accounts to hold. The payer side covers what the payee side cannot: the first victim of a brand-new mule
account, who is only visible from the victim's own session. See `docs/ARCHITECTURE.md`.

> Everything here is trained and evaluated on **synthetic or public data** whose behaviours we wrote ourselves.
> The reports validate the pipelines and show their failure modes; they are not real-world accuracy.

## Layout

```
ml/
  sim/        session simulator (scam workflows + benign look-alikes; mules belong to syndicates)
  campaign/   payee-side layer: ledger, causal features, payee-risk model, campaign tracker, radar, evaluation
  models/     workflow GRU | tabular (IEEE-CIS) | temporal GNN (IBM AML) | behavioural biometrics (HMOG)
  engine/     session fusion (monotone XGBoost) + alert policy (expected-value tiers, anti-fatigue rules)
  reports/    results of every training / evaluation run (campaign.md is the payee-side report)
backend/      FastAPI service: session, campaign, gnn, biometrics, tabular
tests/        pytest (ml + backend)
docs/         ARCHITECTURE.md
DATA/ data/   raw public datasets / generated data (git-ignored)
```

Not built yet: the analyst console UI, the on-device SDK that would collect call/screen-share signals, any
integration with a real bank or PSP.

## Setup (Windows)

```bash
python -m venv ~/envs/raksham          # keep the venv outside OneDrive
source ~/envs/raksham/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt        # needs xgboost>=2.1 (older xgboost cannot load XGBClassifier models under scikit-learn 1.6)
# GPU torch (later): pip install torch --index-url https://download.pytorch.org/whl/cu124
pytest tests -q                        # tests that need trained session models / datasets / CUDA skip themselves
```

## Payee-side layer (`ml/campaign`)

```bash
python -m ml.campaign.evaluate --n-sessions 10000 --save-model    # ~4 min -> ml/reports/campaign.{md,json} + ml/campaign/artifacts/
python -m ml.campaign.attach --sim data/sim_wf                    # write the honest payee score into the session simulator's events
```

After `attach`, add the real biometrics scores and retrain the session models against both:

```bash
python -m ml.models.biometrics.session_scores --sim data/sim_wf   # real HMOG BiLSTM+LDA deviation per touch window
python -m ml.models.workflow.train --seed 0 && python -m ml.engine.oof && python -m ml.engine.fit
python -m ml.engine.simulate     # engine results            -> ml/reports/engine.md
python -m ml.engine.ablation     # what each signal adds     -> ml/reports/ablation.md
python -m ml.engine.robustness   # adaptive scammers (~10 m) -> ml/reports/robustness.md
```

## Session simulator and models

```bash
python -m ml.sim.generate --n-sessions 10000 --scam-rate 0.2 --seed 7 --out data/sim
python -m ml.sim.generate --demo digital_arrest --out data/sim/demo
```

Outputs (parquet): `events`, `sessions`, `users`, `payees` (`payees.syndicate` is the mule's syndicate; a scam session
only pays mules of one syndicate). `events` has one row per event with the session context snapshot (`call_active`,
`caller_kind`, `caller_number`, `caller_reported`, `screen_share_active`, `sideloaded_app_present`, ...); `sessions` has
`typology, is_scam, extraction_ts` (the deadline for a useful alert) and `loss_amount`. Stages:
`contact → pretext → isolation → extraction`.

Two signals come from outside the simulator's own assumptions:
- **Touch**: each customer is mapped to a held-out HMOG subject; every touch window (`BIO_WINDOW`) references 10 real
  gestures (`bio_ref`, `ml/sim/hmog_bank.py`). Someone else's hands (overlay / remote-control fraud) are another HMOG
  subject's real gestures; "coerced" is the customer's own gestures with a documented shift (HMOG has no coercion labels).
- **Caller reputation**: calls carry a number; scam syndicates reuse numbers, a share of which the telecom already has
  on its reported list (`ml/sim/telecom.py`). The API checks numbers by private set intersection
  (`infra/privacy/psi.py`, `reputation.py`) and only if the customer consented (`infra/privacy/consent.py`).

Each session runs on its own random stream, so `generate(..., adversary={...})` (`ml/sim/builder.py ADVERSARY_KNOBS`)
changes only the scam sessions: the robustness worlds share every genuine session with the baseline.

## REST API (`backend/`)

```bash
python -m ml.engine.oof && python -m ml.engine.fit          # once: session fusion artifact
python -m ml.campaign.evaluate --save-model                 # once: payee-risk model
uvicorn backend.app:app --port 8000                         # docs: http://127.0.0.1:8000/docs
python -m backend.bench --url http://127.0.0.1:8000         # latency -> backend/reports/serve_latency.md
```

| endpoint | what it does |
|---|---|
| `GET /health` | loaded services, device, load errors |
| `POST /v1/session/{id}/start` · `/events` | stream raw session events. At `PAYMENT_ATTEMPT`: payee risk (from the campaign service unless the client sends one) → workflow GRU → fusion → alert policy → action, reasons, EN/HI message |
| `POST /v1/demo/{typology}?persona=` | replay a deterministic simulator scenario through the session pipeline (senior / student / professional customer) |
| `POST /v1/consent/check` · `POST /v1/telecom/psi/demo` | DPDP purpose gate (audited); full DH private set intersection between bank numbers and the telecom's reported list |
| `GET /v1/demo/touch` · `GET /v1/demo/numbers` | builder helpers: a real HMOG touch window (own / coerced / someone else's hands); reported and clean demo numbers |
| `POST /v1/payee/score` | payer-side question: how risky is this payee for ₹X? Read-only, with reason codes and the case it belongs to |
| `POST /v1/campaign/ingest` | feed one completed transfer into the payee-side state |
| `POST /v1/campaign/demo/load` | replay the synthetic ledger up to a day (call again with a later day to advance it) |
| `GET /v1/campaign/cases` | cases ranked by recoverable rupees, each with an EN/HI summary and recommended actions |
| `POST /v1/campaign/cases/{id}/hold` · `/v1/campaign/release` | analyst action: transaction-level credit hold (a named analyst is required; never automatic) |
| `POST /v1/gnn/score` | laundering probability of an account-to-account transfer (IBM AML) |
| `POST /v1/biometrics/enroll` · `/verify` | gesture-profile enrolment and BiLSTM+LDA verification (HMOG) |
| `POST /v1/tabular/score` | IEEE-CIS transaction risk from engineered features |
| `POST /v1/admin/reset` | clear session, campaign and GNN state |

Services that fail to load are reported in `/health` and return 503; the rest keep working.
Select services with `RAKSHAM_SERVICES=campaign,session,...`.
