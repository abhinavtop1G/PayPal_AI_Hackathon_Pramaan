# Deploying the authentication service

## Cloud architecture (Google Cloud, Mumbai region)

```
 client SDK (mobile / web)
        │  HTTPS, X-API-Key, X-Timestamp + X-Signature (HMAC-SHA256 of body)
        ▼
 Global HTTPS load balancer ── Cloud Armor (OWASP rules, per-IP rate-based ban)
        │  adds X-Client-Geo-Location: {city},{lat,long}
        ▼
 Cloud Run: pramaan-auth (asia-south1, min 1 instance, autoscale to 10, 2 vCPU / 2 GiB)
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
python run.py                                                  # API on http://127.0.0.1:8000/docs, console on http://localhost:3000
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

Read the generated key: `gcloud secrets versions access latest --secret pramaan-api-keys`.
Benchmark the deployed service: `PRAMAAN_API_KEY=... PRAMAAN_HMAC_SECRET=... python -m backend.bench_auth --url https://<service-url>`.

### Console

Every console route is prerendered static (`npm run build` lists them), so any static host works: Vercel (root
directory `frontend`, with "include files outside the root directory" on, because the console imports `../sdk/web/src`),
Firebase Hosting, or `npm start`. Without `NEXT_PUBLIC_PRAMAAN_API` (set at build time) it plays the recordings in
`frontend/public/data` and needs no API at all. With it, set `RAKSHAM_CORS_ORIGINS=https://<console-domain>` on the API
so the browser may call it.

A secured API answers the browser only on its open paths, so choose them for what the public console should do live:

| console feature | paths |
|---|---|
| decision lab, challenge loop, overview and audit counters | `/v1/auth/demo,/v1/auth/scenarios,/v1/auth/decisions,/v1/auth/stats` |
| live capture: typing and touch verdicts, "enrol me" | add `/v1/keystroke,/v1/biometrics` (demo deployments only: these let anyone enrol profiles) |
| live capture "Decide it", the developers playground | `/v1/authenticate`: only in open development mode; in production the browser never calls it directly |

## Configuration

| variable | meaning |
|---|---|
| `PRAMAAN_SERVICES` | services to load (image default `biometrics,keystroke,campaign,auth`) |
| `PRAMAAN_API_KEYS` | comma-separated client keys; unset = open development mode |
| `PRAMAAN_HMAC_SECRET` | request-signing secret; unset = signatures not required |
| `PRAMAAN_RATE_LIMIT` | requests per second per key / IP (burst 2x) |
| `PRAMAAN_OPEN_PATHS` | prefixes that skip key and signature (public demo console: `/v1/auth/demo,...`) |
| `REDIS_URL` | live state in Redis instead of process memory |
| `DATABASE_URL` | audit log in Postgres instead of SQLite (`PRAMAAN_AUDIT_DB`) |
| `BIO_CALIB` | touch-score calibration file (shipped: `ml/auth/artifacts/bio_calib.pkl`) |
| `RAKSHAM_CORS_ORIGINS` | browser origins allowed to call the API |

## Not verified here

The Dockerfile and `deploy/cloudrun.sh` were written without Docker or gcloud on the development machine, so the image
build and the deploy script have not been run yet. Run `docker compose up --build` (or step 3) once before the demo.
The `torch==2.14.1` CPU wheel pin matches the local environment; change it if the CPU index lacks that version.
