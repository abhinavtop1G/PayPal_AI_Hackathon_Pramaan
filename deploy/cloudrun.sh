#!/usr/bin/env bash
# Deploy the BIOS authentication API to Google Cloud Run in Mumbai (asia-south1), with secrets in Secret Manager,
# live state in Memorystore (Redis) and an HTTPS load balancer with Cloud Armor in front.
#
#   export PROJECT_ID=my-project
#   bash deploy/cloudrun.sh            # steps 1-4: build, secrets, deploy (enough for a working public URL)
#   WITH_REDIS=1 bash deploy/cloudrun.sh      # + Memorystore and a VPC connector (shared state across instances)
#   WITH_ARMOR=1 DOMAIN=api.example.com bash deploy/cloudrun.sh   # + global HTTPS LB, Cloud Armor, geo header
#
# Needs: gcloud (authenticated), billing enabled on the project.
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?set PROJECT_ID}
REGION=${REGION:-asia-south1}
SERVICE=${SERVICE:-bios-auth}
REPO=${REPO:-bios}
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:$(date +%Y%m%d-%H%M%S)"

gcloud config set project "$PROJECT_ID"

# 1. APIs and the image registry ------------------------------------------------------------------------------
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION"

# 2. Build in Cloud Build (no local Docker needed) --------------------------------------------------------------
gcloud builds submit --tag "$IMAGE" .

# 3. Secrets: API key for clients, HMAC secret for request signing ----------------------------------------------
for name in bios-api-keys bios-hmac-secret; do
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    openssl rand -hex 24 | gcloud secrets create "$name" --data-file=- --replication-policy=user-managed --locations="$REGION"
    echo "created secret $name (read it with: gcloud secrets versions access latest --secret $name)"
  fi
done
SA="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
for name in bios-api-keys bios-hmac-secret; do
  gcloud secrets add-iam-policy-binding "$name" --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null
done

# 4. Optional: Memorystore Redis (shared live state) -------------------------------------------------------------
EXTRA_FLAGS=()
# '@' separates variables (gcloud's ^@^ delimiter syntax) because the values themselves contain commas
ENV_VARS="BIOS_SERVICES=biometrics,keystroke,campaign,auth@RAKSHAM_DEVICE=cpu@BIOS_RATE_LIMIT=100"
ENV_VARS+="@BIOS_OPEN_PATHS=/v1/auth/demo,/v1/auth/scenarios,/v1/auth/decisions,/v1/auth/stats"
ENV_VARS+="@RAKSHAM_CORS_ORIGINS=${CORS_ORIGINS:-http://localhost:3000}"
if [[ "${WITH_REDIS:-0}" == "1" ]]; then
  gcloud services enable redis.googleapis.com vpcaccess.googleapis.com
  gcloud redis instances describe bios-state --region "$REGION" >/dev/null 2>&1 || \
    gcloud redis instances create bios-state --size 1 --region "$REGION" --tier basic --redis-version redis_7_2
  gcloud compute networks vpc-access connectors describe bios-conn --region "$REGION" >/dev/null 2>&1 || \
    gcloud compute networks vpc-access connectors create bios-conn --region "$REGION" --range 10.8.0.0/28
  REDIS_HOST=$(gcloud redis instances describe bios-state --region "$REGION" --format 'value(host)')
  ENV_VARS+="@REDIS_URL=redis://${REDIS_HOST}:6379/0"
  EXTRA_FLAGS+=(--vpc-connector bios-conn)
fi

# 5. Deploy: min 1 instance keeps the models warm (no cold-start latency on the first decision) ------------------
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --platform managed \
  --cpu 2 --memory 2Gi --min-instances 1 --max-instances 10 --concurrency 40 --timeout 30 \
  --allow-unauthenticated \
  --set-env-vars "^@^${ENV_VARS}" \
  --set-secrets "BIOS_API_KEYS=bios-api-keys:latest,BIOS_HMAC_SECRET=bios-hmac-secret:latest" \
  ${EXTRA_FLAGS[@]+"${EXTRA_FLAGS[@]}"}

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')
echo "Deployed: $URL   (docs: $URL/docs, health: $URL/health)"

# 6. Optional: global HTTPS load balancer + Cloud Armor (WAF, rate-based ban) + client geo header ------------------
if [[ "${WITH_ARMOR:-0}" == "1" ]]; then
  DOMAIN=${DOMAIN:?set DOMAIN for the managed certificate}
  gcloud compute network-endpoint-groups create bios-neg --region "$REGION" \
    --network-endpoint-type serverless --cloud-run-service "$SERVICE"
  gcloud compute backend-services create bios-backend --global --load-balancing-scheme EXTERNAL_MANAGED
  gcloud compute backend-services add-backend bios-backend --global \
    --network-endpoint-group bios-neg --network-endpoint-group-region "$REGION"
  # the load balancer tells the API where the client is (features: impossible travel, new city)
  gcloud compute backend-services update bios-backend --global \
    --custom-request-header 'X-Client-Geo-Location:{client_city},{client_city_lat_long}'
  gcloud compute security-policies create bios-armor --description "BIOS API WAF"
  gcloud compute security-policies rules create 1000 --security-policy bios-armor \
    --expression "evaluatePreconfiguredExpr('sqli-v33-stable') || evaluatePreconfiguredExpr('xss-v33-stable')" --action deny-403
  gcloud compute security-policies rules create 2000 --security-policy bios-armor --src-ip-ranges '*' \
    --action rate-based-ban --rate-limit-threshold-count 600 --rate-limit-threshold-interval-sec 60 \
    --ban-duration-sec 300 --conform-action allow --exceed-action deny-429 --enforce-on-key IP
  gcloud compute backend-services update bios-backend --global --security-policy bios-armor
  gcloud compute url-maps create bios-lb --default-service bios-backend --global
  gcloud compute ssl-certificates create bios-cert --domains "$DOMAIN" --global
  gcloud compute target-https-proxies create bios-proxy --url-map bios-lb --ssl-certificates bios-cert
  gcloud compute forwarding-rules create bios-https --global --target-https-proxy bios-proxy --ports 443 \
    --load-balancing-scheme EXTERNAL_MANAGED
  echo "Point $DOMAIN at: $(gcloud compute forwarding-rules describe bios-https --global --format 'value(IPAddress)')"
  echo "Then restrict Cloud Run ingress to the load balancer:"
  echo "  gcloud run services update $SERVICE --region $REGION --ingress internal-and-cloud-load-balancing"
fi
