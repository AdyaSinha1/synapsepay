"""SynapsePay deployment smoke test.

Usage:
    python scripts/smoke.py --base-url https://synapsepay-api.onrender.com

Stdlib only. Runs against a live deployment:
  1. health check
  2. register a hirer and a worker
  3. hirer creates + funds a contract (simulated)
  4. worker accepts and submits passing code
  5. arbitrate and assert a settled state
  6. a third user gets 404 on that contract
  7. an unauthenticated call gets 401

Exit code 0 = all green; 1 = any check failed.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def call(base, path, method="GET", body=None, token=None, timeout=90):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode() or "{}")
        except Exception:
            return exc.code, {}


def wait_healthy(base, deadline_s=180):
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        status, _ = call(base, "/api/health")
        if status == 200:
            return True
        time.sleep(5)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    suffix = uuid.uuid4().hex[:8]
    hirer = f"smoke-hirer-{suffix}"
    worker = f"smoke-worker-{suffix}"
    third = f"smoke-third-{suffix}"
    password = "longenough-passphrase"

    failures = []

    def record(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    print(f"smoke: {base}")
    if not wait_healthy(base):
        print("[FAIL] health check — API never returned 200")
        sys.exit(1)
    print("[PASS] health check")

    status, hirer_reg = call(base, "/api/auth/register", "POST", {
        "username": hirer, "password": password, "role": "hirer"})
    record("register hirer", status == 201 or status == 409)
    status, worker_reg = call(base, "/api/auth/register", "POST", {
        "username": worker, "password": password, "role": "worker"})
    record("register worker", status == 201 or status == 409)
    status, third_reg = call(base, "/api/auth/register", "POST", {
        "username": third, "password": password, "role": "hirer"})
    record("register third user", status == 201 or status == 409)

    if status not in (201, 409):
        record("register third user", False, "cannot continue without accounts")
        sys.exit(1)

    _, hirer_login = call(base, "/api/auth/login", "POST", {"username": hirer, "password": password})
    _, worker_login = call(base, "/api/auth/login", "POST", {"username": worker, "password": password})
    _, third_login = call(base, "/api/auth/login", "POST", {"username": third, "password": password})
    hirer_tok, worker_tok, third_tok = (hirer_login.get("token"), worker_login.get("token"),
                                        third_login.get("token"))

    status, created = call(base, "/api/contracts/create", "POST", {
        "title": f"smoke contract {suffix}",
        "bounty_value": 25,
        "test_code": ("def test_a():\n    assert True\ndef test_b():\n    assert True\n"
                      "def test_c():\n    assert True\n"),
        "run_now": False,
    }, token=hirer_tok)
    record("create + fund contract (simulated)", status == 200, str(created.get("detail", ""))[:120])
    cid = created.get("contract", {}).get("id")

    status, _ = call(base, f"/api/contracts/{cid}/accept", "POST", {}, token=worker_tok)
    record("worker accepts", status == 200)

    status, _ = call(base, f"/api/contracts/{cid}/submit", "POST", {
        "artifact_type": "code",
        "code": "def solve():\n    '''passing submission'''\n    return True\n",
    }, token=worker_tok)
    record("worker submits", status == 200)

    status, arbitrated = call(base, f"/api/contracts/{cid}/arbitrate", "POST", {}, token=hirer_tok)
    settled = arbitrated.get("escrow", {}).get("status") in ("CAPTURED", "SETTLED", "PARTIAL")
    record("arbitrate settles", status == 200 and settled,
           f"status={arbitrated.get('escrow', {}).get('status')}")

    status, _ = call(base, f"/api/contracts/{cid}", "GET", token=third_tok)
    record("third user gets 404 on contract", status == 404, f"got {status}")

    status, _ = call(base, "/api/contracts", "GET")
    record("unauthenticated call gets 401", status == 401, f"got {status}")

    print(f"\nsmoke: {len(CHECKS) + 2 - len(failures)} checks passed, {len(failures)} failed")
    if failures:
        print("FAILED:", ", ".join(failures))
        sys.exit(1)
    print("smoke: ALL GREEN")


if __name__ == "__main__":
    main()
