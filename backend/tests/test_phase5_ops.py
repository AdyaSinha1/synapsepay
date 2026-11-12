"""Phase 5: security & operations — DB-backed login throttle, security
headers, request IDs, no-trace 500s, and open-contract caps."""

import uuid

import app.database as database_module
from app import config


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_failed_logins_are_throttled_and_persisted(tmp_path):
    from app import db
    from app.database import SessionLocal
    from app.orm import AuthThrottleRow

    db.init(str(tmp_path / "throttle.db"))
    try:
        client = _client()
        username = f"throttle-{uuid.uuid4().hex[:8]}"
        assert client.post("/api/auth/register", json={
            "username": username, "password": "longenough1",
        }).status_code == 201

        got_429 = False
        for i in range(config.LOGIN_THROTTLE_LIMIT + 5):
            resp = client.post("/api/auth/login", json={
                "username": username, "password": f"definitely-wrong-{i}",
            })
            if resp.status_code == 429:
                got_429 = True
                break
            assert resp.status_code == 401
        assert got_429, "failed logins must trip the DB-backed throttle"

        with database_module.SessionLocal() as session:
            rows = session.query(AuthThrottleRow).filter(AuthThrottleRow.ok.is_(False)).all()
            assert len(rows) >= config.LOGIN_THROTTLE_LIMIT, "attempts must be persisted in the database"

        with database_module.SessionLocal() as session:
            assert client.post("/api/auth/login", json={
                "username": username, "password": "longenough1",
            }).status_code in (200, 429), "throttle may still be active but rows survive restarts"
    finally:
        db.close()


def test_successful_login_never_counts_toward_throttle(tmp_path):
    from app import db

    db.init(str(tmp_path / "throttle-ok.db"))
    try:
        client = _client()
        username = f"ok-{uuid.uuid4().hex[:8]}"
        assert client.post("/api/auth/register", json={
            "username": username, "password": "longenough1",
        }).status_code == 201
        for _ in range(config.LOGIN_THROTTLE_LIMIT + 2):
            resp = client.post("/api/auth/login", json={
                "username": username, "password": "longenough1",
            })
            assert resp.status_code == 200, "successful logins must never be throttled"
    finally:
        db.close()


def test_security_headers_and_request_ids_present():
    client = _client()
    r1 = client.get("/api/health")
    r2 = client.get("/api/health")
    assert r1.headers.get("x-content-type-options") == "nosniff"
    assert r1.headers.get("x-frame-options") == "DENY"
    assert r1.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    id1 = r1.headers.get("x-request-id")
    id2 = r2.headers.get("x-request-id")
    assert id1 and id2 and id1 != id2


def test_500_returns_json_without_stack_trace(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    def explode():
        raise RuntimeError("boom — internal detail that must never reach the client")

    monkeypatch.setattr("app.main.compute_metrics", explode)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/metrics")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "internal server error"
    assert "boom" not in resp.text and "RuntimeError" not in resp.text
    assert "request_id" in body


def test_open_contract_cap_enforced(tmp_path):
    from fastapi.testclient import TestClient

    from app import db
    from app.agent_simulator import CONTRACTS, ESCROWS
    from app.main import app
    from app.models import TaskContract

    db.init(str(tmp_path / "cap.db"))
    try:
        monkey_username = f"cap-{uuid.uuid4().hex[:8]}"
        with TestClient(app) as client:
            reg = client.post("/api/auth/register", json={
                "username": monkey_username, "password": "longenough1", "role": "hirer",
            })
            token = reg.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            owned = []
            for i in range(config.OPEN_CONTRACT_CAP):
                resp = client.post("/api/contracts/create", headers=headers, json={
                    "title": f"cap contract {i}",
                    "bounty_value": 5.0,
                    "test_code": (
                        "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
                        "def test_c():\n    assert True\n"
                    ),
                    "run_now": False,
                })
                assert resp.status_code == 200, resp.text
                owned.append(resp.json()["contract"]["id"])

            resp = client.post("/api/contracts/create", headers=headers, json={
                "title": "one too many",
                "bounty_value": 5.0,
                "test_code": (
                    "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
                    "def test_c():\n    assert True\n"
                ),
                "run_now": False,
            })
            assert resp.status_code == 429
            assert "cap" in resp.json()["detail"]

            # a different account is not affected by the first user's cap
            other = f"cap2-{uuid.uuid4().hex[:8]}"
            other_reg = client.post("/api/auth/register", json={
                "username": other, "password": "longenough1",
            })
            other_headers = {"Authorization": f"Bearer {other_reg.json()['token']}"}
            ok = client.post("/api/contracts/create", headers=other_headers, json={
                "title": "second user fine", "bounty_value": 5.0, "run_now": False,
                "test_code": (
                    "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
                    "def test_c():\n    assert True\n"
                ),
            })
            assert ok.status_code == 200
    finally:
        db.close()
