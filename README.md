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
| **risk engine (all signals)** | **1.8%** | **0.08%** | **82.8%** | **83.4%** |
| behaviour signals only (touch + typing + session) | 2.0% | 0.10% | 71.9% | 79.0% |
| device signals only | 0.7% | 0.04% | 50.2% | 51.4% |
| transaction signals only | 4.8% | 0.23% | 76.4% | 79.4% |
| SMS OTP on every payment | 100% | 3.0% | 24.2% | 24.0% |
| rules engine + SMS OTP | 3.7% | 0.12% | 30.2% | 31.1% |

* Test ROC-AUC 0.996 (all signals) vs 0.88 / 0.76 / 0.95 for one family alone. Adding typing rhythm lifted the
  behaviour family from ROC-AUC 0.80 to 0.88 and from 62.8% to 71.9% of attacks stopped with half the challenges; on
  the full engine it is neutral in ranking (0.996 vs 0.997) and moves the operating point to fewer genuine challenges
  (1.8% vs 2.0%) and slightly fewer attack requests stopped (82.8% vs 85.8%), mostly coached victims, whose own typing
  looks normal.
* Per attack (finally stopped): stolen credentials 100%, SIM swap 100%, bots 100%, remote-access takeover 90%,
  **coached victim 46%** (the real owner on their own phone is the hardest case). Hard-difficulty attacks: 68%.
* Typing rhythm (`ml/reports/keystroke_cmu.md`): a 1D-CNN keystroke encoder trained on the CMU DSL-StrongPassword
  data (51 people typing `.tie5Roanl`). On people it never saw, enrolled on 4 earlier sessions and tested on 4 later
  ones: per-user EER 13.0% (scaled Manhattan 19.9%; fused 12.2%, 8.5% over 3 tries). Our scaled Manhattan reproduces
  the published 9.6% on the paper's own protocol. In the service it is the `typing_dev` behaviour signal for password /
  PIN entry, on web as well as mobile.
* Device binding: the first payment from a device never seen on the account is always stepped up (passkey on the
  registered phone when one exists or the SIM just changed), however low the model's risk.
* Latency over HTTP on a laptop **CPU** with API-key + HMAC checks: **p95 42 ms** (no touch data),
  **p95 69 ms** with 10 touch gestures verified by the BiLSTM. In-process decision (features + model + SHAP + policy): p95 18 ms. (HTTP figures measured before the typing
  signal; the 84k-parameter typing CNN adds a CPU forward pass per attempt.)

## Layout

```
ml/models/keystroke/  1D-CNN typing-rhythm encoder (CMU keystroke data): data, model, train, evaluate, scorer
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
BIOS_SERVICES=biometrics,keystroke,campaign,auth uvicorn backend.app:app --port 8000

# console on http://localhost:3000 (without NEXT_PUBLIC_BIOS_API it plays the recorded scenarios)
cd frontend && npm ci && NEXT_PUBLIC_BIOS_API=http://127.0.0.1:8000 npm run dev
```

On Windows Git Bash, prefix commands that set path-like env values (e.g. `BIOS_OPEN_PATHS=/v1/...`) with
`MSYS_NO_PATHCONV=1`, otherwise Git Bash rewrites them into Windows paths.

Rebuild everything from data:

```bash
python -m ml.models.biometrics.data      # HMOG gesture cache from DATA/hmog_dataset.zip (once)
python -m ml.models.keystroke.train --seed 0   # 1D-CNN typing encoder (seeds 0-2, ~2 min each, CUDA optional)
python -m ml.models.keystroke.evaluate   # held-out users vs baselines -> ml/reports/keystroke_cmu.md + artefact
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
| `POST /v1/keystroke/enroll` | enrol a user's typing rhythm (≥ 5 password / PIN attempts, 31 key timings each) |
| `GET /v1/auth/decisions` · `/v1/auth/stats` | audit feed and counters (decisions, challenge mix, p50/p95 latency) |
| `GET /v1/auth/scenarios` · `POST /v1/auth/demo/{scenario}` · `POST /v1/auth/demo/verify` | demo customer (open paths for the public console) |
| `GET /health` | loaded services, security mode, model version, state / audit backends |

Security (env-configured, see `docs/DEPLOY.md`): `X-API-Key`; `X-Timestamp` + `X-Signature` = HMAC-SHA256 of
`"<timestamp>.<body>"` with 5-minute window and replay rejection; per-key token-bucket rate limit; TLS at the load balancer.
