# PRAMAAN transaction-authentication API — CPU image for Google Cloud Run (or any container host).
#   docker build -t pramaan-auth .
#   docker run -p 8080:8080 -e PRAMAAN_API_KEYS=dev-key pramaan-auth
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    RAKSHAM_DEVICE=cpu \
    PRAMAAN_SERVICES=biometrics,keystroke,campaign,auth \
    BIO_CALIB=ml/auth/artifacts/bio_calib.pkl \
    PRAMAAN_AUDIT_DB=/tmp/audit.sqlite \
    OMP_NUM_THREADS=2

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-serve.txt .
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements-serve.txt

COPY backend backend
COPY infra infra
COPY ml ml

# non-root
RUN useradd -m app && chown -R app /app
USER app

EXPOSE 8080
CMD exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 75
