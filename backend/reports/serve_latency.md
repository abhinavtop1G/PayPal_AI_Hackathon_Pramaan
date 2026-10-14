# API latency (end-to-end HTTP, keep-alive, single client)

Server device: cuda; services: biometrics, gnn, session, tabular. Client-side wall time incl. JSON/HTTP overhead, localhost, RTX 4070 laptop.

| endpoint | n | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|
| GET /health | 300 | 11.3 | 15.3 | 17.1 |
| POST /v1/session/{id}/events (non-payment) | 322 | 40.0 | 48.8 | 54.0 |
| POST /v1/session/{id}/events (PAYMENT_ATTEMPT: GRU + fusion + policy) | 42 | 54.9 | 60.9 | 63.3 |
| POST /v1/gnn/score | 300 | 23.0 | 29.8 | 35.1 |
| POST /v1/biometrics/verify (20 gestures) | 300 | 15.2 | 20.3 | 22.3 |
| POST /v1/tabular/score (1 txn) | 300 | 15.1 | 17.9 | 19.1 |
| POST /v1/tabular/score (100 txns) | 30 | 14.2 | 16.4 | 16.8 |
