# Deploying the authentication service

## Cloud architecture (Google Cloud, Mumbai region)

```
 client SDK (mobile / web)
        │  HTTPS, X-API-Key, X-Timestamp + X-Signature (HMAC-SHA256 of body)
        ▼
 Global HTTPS load balancer ── Cloud Armor (OWASP rules, per-IP rate-based ban)
        │  adds X-Client-Geo-Location: {city},{lat,long}
        ▼
 Cloud Run: bios-auth (asia-south1, min 1 instance, autoscale to 10, 2 vCPU / 2 GiB)
   FastAPI ── SecurityMiddleware (key, signature, replay, token-bucket rate limit)
           ── /v1/authenticate → touch verifier (BiLSTM+LDA) → payee intelligence → features → XGBoost → policy
        │                         │                                 │
        ▼                         ▼                                 ▼
 Memorystore Redis          Cloud SQL Postgres                Secret Manager
 (users / devices / IPs,    (audit log of every decision     (API keys, HMAC secret)
  pending challenges)        and challenge result)
```

All data stays in `asia-south1` (RBI payment-data localisation). Model files ship inside the image
(`ml/auth/artifacts`, `ml/models/biometrics/artifacts`, `ml/campaign/artifacts`); no dataset is needed at runtime.

## 1. Run locally without Docker

```bash
source ~/envs/raksham/Scripts/activate
BIOS_SERVICES=biometrics,campaign,auth uvicorn backend.app:app --port 8000     # http://127.0.0.1:8000/docs
cd frontend && NEXT_PUBLIC_BIOS_API=http://127.0.0.1:8000 npm run dev          # console on http://localhost:3000
python -m backend.bench_auth --url http://127.0.0.1:8000                       # latency -> backend/reports/auth_latency.md
```

## 2. Run the cloud stack locally (Docker)

```bash
docker compose up --build        # API + Redis + Postgres, API on http://localhost:8080
```

## 3. Deploy to Cloud Run

```bash
export PROJECT_ID=<your-project>
bash deploy/cloudrun.sh                                   # build (Cloud Build), secrets, deploy → prints the URL
WITH_REDIS=1 bash deploy/cloudrun.sh                      # + Memorystore (shared state across instances)
WITH_ARMOR=1 DOMAIN=api.example.com bash deploy/cloudrun.sh   # + HTTPS load balancer, Cloud Armor, geo header
```

Read the generated key: `gcloud secrets versions access latest --secret bios-api-keys`.
Benchmark the deployed service: `BIOS_API_KEY=... BIOS_HMAC_SECRET=... python -m backend.bench_auth --url https://<service-url>`.

Frontend: `cd frontend && NEXT_PUBLIC_BIOS_API=https://<service-url> npm run build` and host it on Vercel / Firebase
Hosting, or run it without the env variable to play the recorded scenarios (`python -m backend.record_auth_demo`).
Set `CORS_ORIGINS=https://<console-domain>` when deploying the API so the browser may call it.

## Configuration

| variable | meaning |
|---|---|
| `BIOS_SERVICES` | services to load (image default `biometrics,campaign,auth`) |
| `BIOS_API_KEYS` | comma-separated client keys; unset = open development mode |
| `BIOS_HMAC_SECRET` | request-signing secret; unset = signatures not required |
| `BIOS_RATE_LIMIT` | requests per second per key / IP (burst 2x) |
| `BIOS_OPEN_PATHS` | prefixes that skip key and signature (public demo console: `/v1/auth/demo,...`) |
| `REDIS_URL` | live state in Redis instead of process memory |
| `DATABASE_URL` | audit log in Postgres instead of SQLite (`BIOS_AUDIT_DB`) |
| `BIO_CALIB` | touch-score calibration file (shipped: `ml/auth/artifacts/bio_calib.pkl`) |
| `RAKSHAM_CORS_ORIGINS` | browser origins allowed to call the API |

## Not verified here

The Dockerfile and `deploy/cloudrun.sh` were written without Docker or gcloud on the development machine, so the image
build and the deploy script have not been run yet. Run `docker compose up --build` (or step 3) once before the demo.
The `torch==2.14.1` CPU wheel pin matches the local environment; change it if the CPU index lacks that version.
