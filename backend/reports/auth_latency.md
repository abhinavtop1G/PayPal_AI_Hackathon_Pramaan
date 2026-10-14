# /v1/authenticate latency (end-to-end HTTP, keep-alive, single client)

Target: http://127.0.0.1:8011; device: cpu; services: auth, biometrics, campaign; security: secured; state: memory.
Client-side wall time incl. JSON/HTTP + API key + HMAC check.

| endpoint | n | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|
| POST /v1/authenticate (no touch data) | 300 | 36.3 | 42.5 | 89.3 |
| POST /v1/authenticate (+10 touch gestures verified) | 300 | 52.7 | 69.1 | 118.4 |
