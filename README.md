# BIOS — fast and secure online transaction authentication

A cloud risk-authentication service: for every login or payment it combines **behaviour**, **device information**
and **transaction patterns**, decides **allow / challenge / block** in real time, picks the challenge that actually
stops the likely attack, and returns **the signals behind the decision**.

```
POST /v1/authenticate  →  { decision, risk_score, challenge_type, reasons (EN/HI), signals (tree-SHAP), latency_ms }
POST /v1/challenge/verify  →  passed: allow (+ trust the device) · failed: block, lock 30 min
```

Built on the RAKSHAM scam-detection work (IIT Delhi): its touch-biometrics model, payee-risk model and API skeleton
are reused; the scam-session demo is kept at `/scam` in the console and documented in `docs/README_RAKSHAM.md`.

> Attack and genuine behaviours are **simulated**; touch windows are **real** HMOG gestures scored by the real model;
> challenge efficacies are **assumptions**. The numbers validate the service and compare designs, not real-world accuracy.

## Results (`ml/reports/auth.md`, `backend/reports/auth_latency.md`)

3,000 simulated customers, 273k requests over 60 days; trained on days 0–35, test days 45–60 replayed through the
service, including simulated challenge outcomes.

| design | genuine requests challenged | genuine finally blocked | attack requests stopped | attack money stopped |
|---|---|---|---|---|
| **risk engine (all signals)** | **2.0%** | **0.09%** | **85.8%** | **87.4%** |
| behaviour signals only | 3.9% | 0.14% | 62.8% | 65.2% |
| device signals only | 0.7% | 0.04% | 50.2% | 51.4% |
| transaction signals only | 4.8% | 0.23% | 76.4% | 79.4% |
| SMS OTP on every payment | 100% | 3.0% | 24.2% | 24.0% |
| rules engine + SMS OTP | 3.7% | 0.12% | 30.2% | 31.1% |

* Test ROC-AUC 0.997 (all signals) vs 0.80 / 0.76 / 0.95 for one family alone.
* Per attack (finally stopped): stolen credentials 100%, SIM swap 100%, bots 100%, remote-access takeover 87%,
  **coached victim 59%** (the real owner on their own phone is the hardest case). Hard-difficulty attacks: 73%.
* Device binding: the first payment from a device never seen on the account is always stepped up (passkey on the
  registered phone when one exists or the SIM just changed), however low the model's risk.
* Latency over HTTP on a laptop **CPU** with API-key + HMAC checks: **p95 42 ms** (no touch data),
  **p95 69 ms** with 10 touch gestures verified by the BiLSTM. In-process decision (features + model + SHAP + policy): p95 13 ms.

## Layout

```
ml/auth/          the authentication service core (BIOS)
  geo.py            IP intelligence (hosting / anonymiser ranges), distances, load-balancer geo header
  state.py          live state: users, device registry, per-device / per-IP fan-out, pending challenges (memory | Redis)
  features.py       26 causal features: behaviour 5 · device 13 · transaction 8
  sim.py            account-takeover simulator (genuine look-alikes + 5 attacks, difficulty knob, real HMOG touch)
  model.py          monotone XGBoost, prior correction, tree-SHAP
  policy.py         challenge choice (sms_otp | passkey | bank_callback | cool_off) + expected-cost decision
  engine.py         decision + challenge loop
  evaluate.py       training + replay evaluation -> ml/reports/auth.md
  demo.py           demo customer and scenarios; packed real gestures for containers
backend/          FastAPI: app.py, auth_service.py, security.py (keys, HMAC, replay, rate limit), audit.py
frontend/         Next.js console: / (authentication) and /scam (RAKSHAM scam-session layer)
deploy/           cloudrun.sh (Cloud Run, Secret Manager, Memorystore, load balancer + Cloud Armor)
Dockerfile, docker-compose.yml, requirements-serve.txt
ml/models, ml/campaign, ml/engine, ml/sim   RAKSHAM components (touch biometrics, payee risk, scam sessions)
docs/             ARCHITECTURE.md (BIOS), DEPLOY.md, ARCHITECTURE_RAKSHAM.md, README_RAKSHAM.md
tests/            pytest (100 tests; tests/test_auth.py covers the BIOS service)
```

## Run it

```bash
source ~/envs/raksham/Scripts/activate
pip install -r requirements.txt          # + torch (CUDA or CPU build)

# API (touch biometrics + payee intelligence + authentication); docs at http://127.0.0.1:8000/docs
BIOS_SERVICES=biometrics,campaign,auth uvicorn backend.app:app --port 8000

# console on http://localhost:3000 (without NEXT_PUBLIC_BIOS_API it plays the recorded scenarios)
cd frontend && npm ci && NEXT_PUBLIC_BIOS_API=http://127.0.0.1:8000 npm run dev
```

On Windows Git Bash, prefix commands that set path-like env values (e.g. `BIOS_OPEN_PATHS=/v1/...`) with
`MSYS_NO_PATHCONV=1`, otherwise Git Bash rewrites them into Windows paths.

Rebuild everything from data:

```bash
python -m ml.models.biometrics.data      # HMOG gesture cache from DATA/hmog_dataset.zip (once)
python -m ml.auth.evaluate               # simulate, train, evaluate (~12 min) -> ml/reports/auth.md + model
python -m ml.auth.demo                   # packed demo gestures
python -m backend.record_auth_demo       # console recording -> frontend/public/data/auth_demo.json
python -m backend.bench_auth --url http://127.0.0.1:8000     # HTTP latency -> backend/reports/auth_latency.md
pytest tests -q
```

Cloud deployment: `docs/DEPLOY.md` (Docker / Cloud Run in Mumbai, asia-south1). The Dockerfile and deploy script
have not been run on this machine yet (no Docker or gcloud installed).

## API

| endpoint | what it does |
|---|---|
| `POST /v1/authenticate` | decide a login / payment: decision, risk, challenge type, EN/HI reasons, all signal contributions |
| `POST /v1/challenge/verify` | result of the step-up → final allow / block; passkey or call-back makes the device trusted |
| `POST /v1/biometrics/enroll` | enrol a user's touch profile (≥ 20 gestures) |
| `GET /v1/auth/decisions` · `/v1/auth/stats` | audit feed and counters (decisions, challenge mix, p50/p95 latency) |
| `GET /v1/auth/scenarios` · `POST /v1/auth/demo/{scenario}` · `POST /v1/auth/demo/verify` | demo customer (open paths for the public console) |
| `GET /health` | loaded services, security mode, model version, state / audit backends |

Security (env-configured, see `docs/DEPLOY.md`): `X-API-Key`; `X-Timestamp` + `X-Signature` = HMAC-SHA256 of
`"<timestamp>.<body>"` with 5-minute window and replay rejection; per-key token-bucket rate limit; TLS at the load balancer.
