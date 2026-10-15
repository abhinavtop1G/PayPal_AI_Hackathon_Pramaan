"""Append-only audit log of every authentication decision and challenge result.

Writes go through a queue to a background thread, so the decision path never waits on the database:
  * Postgres (Cloud SQL) when DATABASE_URL is set (needs `psycopg`), otherwise
  * SQLite at PRAMAAN_AUDIT_DB (default checkpoints/audit.sqlite).
The last 1,000 records are also kept in memory for the analyst dashboard (`recent`, `stats`).
"""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
from collections import Counter, deque
from pathlib import Path

DDL = """CREATE TABLE IF NOT EXISTS auth_audit (
  id SERIAL_OR_AUTO, ts DOUBLE PRECISION, kind TEXT, decision_id TEXT, user_id TEXT, decision TEXT,
  risk_score DOUBLE PRECISION, challenge_type TEXT, amount DOUBLE PRECISION, latency_ms DOUBLE PRECISION, payload TEXT)"""
COLS = ("ts", "kind", "decision_id", "user_id", "decision", "risk_score", "challenge_type", "amount", "latency_ms", "payload")


class AuditLog:
    def __init__(self, url: str | None = None, sqlite_path: str | None = None):
        self.url = url if url is not None else os.environ.get("DATABASE_URL")
        self.path = sqlite_path or os.environ.get("PRAMAAN_AUDIT_DB", "checkpoints/audit.sqlite")
        self.backend = "postgres" if self.url else "sqlite"
        self.mem: deque = deque(maxlen=1000)
        self.q: queue.Queue = queue.Queue(maxsize=10000)
        self.dropped = 0
        self.written = 0
        self.error: str | None = None
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def __call__(self, record: dict):
        self.mem.append(record)
        try:
            self.q.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    # ------------------------------------------------------------------ writer
    def _connect(self):
        if self.backend == "postgres":
            import psycopg
            con = psycopg.connect(self.url, autocommit=True)
            con.execute(DDL.replace("SERIAL_OR_AUTO", "BIGSERIAL PRIMARY KEY"))
            return con, "%s"
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(DDL.replace("id SERIAL_OR_AUTO", "id INTEGER PRIMARY KEY AUTOINCREMENT"))
        return con, "?"

    def _run(self):
        try:
            con, ph = self._connect()
        except Exception as e:  # keep serving; the in-memory log still works
            self.error = f"{type(e).__name__}: {e}"
            return
        sql = f"INSERT INTO auth_audit ({', '.join(COLS)}) VALUES ({', '.join([ph] * len(COLS))})"
        while True:
            r = self.q.get()
            try:
                con.execute(sql, (r.get("ts"), r.get("kind"), r.get("decision_id"), r.get("user_id"), r.get("decision"),
                                  r.get("risk_score"), r.get("challenge_type"), r.get("amount"), r.get("latency_ms"),
                                  json.dumps(r, default=str)))
                self.written += 1
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"

    # ------------------------------------------------------------------ dashboard
    def recent(self, limit: int = 50, kind: str | None = None) -> list[dict]:
        rows = [r for r in reversed(self.mem) if kind is None or r.get("kind") == kind]
        return rows[:limit]

    def stats(self) -> dict:
        dec = [r for r in self.mem if r.get("kind") == "decision"]
        lat = sorted(r["latency_ms"] for r in dec if r.get("latency_ms") is not None)
        pct = (lambda q: round(lat[min(len(lat) - 1, int(q * len(lat)))], 2) if lat else None)
        return {"decisions": len(dec), "by_decision": dict(Counter(r["decision"] for r in dec)),
                "challenge_types": dict(Counter(r["challenge_type"] for r in dec if r.get("challenge_type"))),
                "challenges_resolved": dict(Counter(r["decision"] for r in self.mem if r.get("kind") == "challenge")),
                "latency_ms": {"p50": pct(0.5), "p95": pct(0.95)}, "backend": self.backend, "written": self.written,
                "dropped": self.dropped, "error": self.error}
