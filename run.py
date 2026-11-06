#!/usr/bin/env python3
"""Start the PRAMAAN API and console together.

    python run.py                # API on http://127.0.0.1:8000, console on http://localhost:3000
    python run.py --api-only     # only the API (docs at http://127.0.0.1:8000/docs)

Install the Python dependencies first (see README.md). Ctrl+C stops everything.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
SERVICES = "biometrics,keystroke,campaign,session,auth,paypal"  # everything the console calls
REQUIRED = ("torch", "xgboost", "sklearn", "pandas", "fastapi", "uvicorn", "httpx")
API_START_TIMEOUT_S = 240


def fail(message: str) -> None:
    sys.exit(f"\n{message}\n")


def check_python_deps() -> None:
    missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
    if missing:
        fail(f"Missing Python packages: {', '.join(missing)}. This interpreter is {sys.executable}.\n"
             "Install them with the setup commands in README.md, then run this script with the same interpreter.")


def check_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            fail(f"Port {port} is already in use. Stop whatever is on it, or pick another with --api-port / --web-port.")


def read_dotenv(path: Path) -> dict[str, str]:
    """KEY=value lines from .env (the PayPal sandbox credentials). Real environment variables win over it."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip("'\"")
    return out


def report_paypal(api_url: str) -> None:
    messages = {"connected": "PayPal sandbox: connected.",
                "not_configured": "PayPal sandbox: no credentials in .env, so the checkout page shows decisions but no PayPal button. "
                                  "See \"Connect PayPal\" in README.md.",
                "bad_credentials": "PayPal sandbox: PayPal rejected the credentials in .env. Check PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET.",
                "unreachable": "PayPal sandbox: could not reach PayPal. Check your internet connection."}
    try:
        with urllib.request.urlopen(f"{api_url}/v1/paypal/config", timeout=30) as r:
            print(messages.get(json.load(r).get("status"), "PayPal sandbox: unknown status."), flush=True)
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        print("PayPal sandbox: could not read its status from the API.", flush=True)


def spawn(cmd: list[str], env: dict[str, str], cwd: Path) -> subprocess.Popen:
    # own process group on POSIX, so stop() also reaches the children npm starts
    return subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=os.name != "nt")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        os.killpg(proc.pid, signal.SIGTERM)


def wait_for_api(proc: subprocess.Popen, url: str) -> dict:
    deadline = time.time() + API_START_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            fail(f"The API exited during startup (code {proc.returncode}). See the output above.")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(1)
    stop(proc)
    fail(f"The API did not answer within {API_START_TIMEOUT_S} s.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Start the PRAMAAN API and console together.")
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=3000)
    ap.add_argument("--api-only", action="store_true", help="start only the API")
    args = ap.parse_args()

    check_python_deps()
    check_port_free(args.api_port)
    npm = None
    if not args.api_only:
        check_port_free(args.web_port)
        npm = shutil.which("npm")
        if npm is None:
            fail("npm was not found. Install Node.js 20 or newer, or use --api-only.")

    api_url = f"http://127.0.0.1:{args.api_port}"
    api_env = {**read_dotenv(ROOT / ".env"), **os.environ, "PRAMAAN_SERVICES": SERVICES, "BIO_CALIB": "ml/auth/artifacts/bio_calib.pkl",
               "RAKSHAM_CORS_ORIGINS": f"http://localhost:{args.web_port},http://127.0.0.1:{args.web_port}"}
    procs: list[subprocess.Popen] = []
    try:
        print(f"Starting the API on {api_url} (loading the models takes up to a minute)...", flush=True)
        api = spawn([sys.executable, "-m", "uvicorn", "backend.app:app", "--port", str(args.api_port)], api_env, ROOT)
        procs.append(api)
        health = wait_for_api(api, api_url)
        print(f"API ready. Services: {', '.join(health.get('loaded', []))}", flush=True)
        for name, error in health.get("errors", {}).items():
            print(f"  WARNING: service '{name}' did not load: {error}", flush=True)
        print(f"API docs: {api_url}/docs", flush=True)
        report_paypal(api_url)

        if npm is not None:
            if not (FRONTEND / "node_modules").exists():
                print("Installing the console's dependencies (first run only)...", flush=True)
                subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)
            web_env = {**os.environ, "NEXT_PUBLIC_PRAMAAN_API": api_url}
            procs.append(spawn([npm, "run", "dev", "--", "--port", str(args.web_port)], web_env, FRONTEND))
            print(f"\nOpen http://localhost:{args.web_port}  (Ctrl+C stops everything)\n", flush=True)

        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        print("A process exited; stopping the rest.", flush=True)
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        for p in procs:
            stop(p)


if __name__ == "__main__":
    main()
