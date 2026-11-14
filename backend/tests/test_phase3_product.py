"""Phase 3 backend seams: worker acceptance, sandbox preview for the wizard,
recent-events feed, and account management (password change, logout-everywhere).
"""

from datetime import datetime, timezone

import pytest
import uuid

from app import config


def test_accept_moves_funded_contract_to_accepted():
    from fastapi.testclient import TestClient

    from app.agent_simulator import CONTRACTS, ESCROWS, build_contract_from_scenario
    from app.main import app
    from app.models import EscrowRecord

    with TestClient(app) as client:
        contract = build_contract_from_scenario("A")
        escrow = EscrowRecord(
            contract_id=contract.id, order_id="ORD-ACC", authorization_id="AUTH-ACC",
            amount=75.0, status="AUTHORIZED", mode="simulated",
        )
        CONTRACTS[contract.id] = contract
        ESCROWS[contract.id] = escrow
        try:
            username = f"worker-{uuid.uuid4().hex[:8]}"
            token = client.post("/api/auth/register", json={
                "username": username, "password": "longenough1", "role": "worker",
            }).json()["token"]
            resp = client.post(
                f"/api/contracts/{contract.id}/accept",
                json={"worker": username},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["contract"]["state"] == "ACCEPTED"
            assert resp.json()["contract"]["worker"] == username
            assert resp.json()["contract"]["worker_id"]
        finally:
            CONTRACTS.pop(contract.id, None)
            ESCROWS.pop(contract.id, None)


def test_accept_rejects_draft_and_settled_contracts():
    from fastapi.testclient import TestClient

    from app.agent_simulator import CONTRACTS, build_contract_from_scenario
    from app.main import app

    with TestClient(app) as client:
        draft = build_contract_from_scenario("A")
        draft.state = "DRAFT"
        CONTRACTS[draft.id] = draft
        settled = build_contract_from_scenario("B")
        settled.state = "SETTLED"
        CONTRACTS[settled.id] = settled
        try:
            username = f"worker-{uuid.uuid4().hex[:8]}"
            token = client.post("/api/auth/register", json={
                "username": username, "password": "longenough1", "role": "worker",
            }).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            assert client.post(f"/api/contracts/{draft.id}/accept", json={}, headers=headers).status_code == 409
            assert client.post(f"/api/contracts/{settled.id}/accept", json={}, headers=headers).status_code == 409
        finally:
            CONTRACTS.pop(draft.id, None)
            CONTRACTS.pop(settled.id, None)


def test_submit_marks_contract_submitted():
    from fastapi.testclient import TestClient

    from app.agent_simulator import CONTRACTS, build_contract_from_scenario
    from app.main import app

    with TestClient(app) as client:
        contract = build_contract_from_scenario("A")
        contract.state = "ACCEPTED"
        CONTRACTS[contract.id] = contract
        try:
            resp = client.post(f"/api/contracts/{contract.id}/submit", json={
                "artifact_type": "code", "code": "def calculate_tiered_fee(a, b):\n    return 0.99\n",
            })
            assert resp.status_code == 200, resp.text
            assert CONTRACTS[contract.id].state == "SUBMITTED"
        finally:
            CONTRACTS.pop(contract.id, None)


def test_sandbox_preview_runs_without_persistence():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/sandbox/preview", json={
            "code": "def add(a, b):\n    return a + b\n",
            "tests": "def test_ok():\n    assert add(1, 1) == 2\n",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["passed"] == 1
        assert body["total"] == 1
        assert body["pass_rate"] == 1.0


def test_password_change_and_logout_everywhere():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        username = f"pw-{__import__('uuid').uuid4().hex[:8]}"
        reg = client.post("/api/auth/register", json={"username": username, "password": "old-password-1"})
        assert reg.status_code == 201
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        wrong = client.post("/api/auth/password", headers=headers, json={
            "old_password": "nope-not-it", "new_password": "new-password-99",
        })
        assert wrong.status_code in (400, 401)

        changed = client.post("/api/auth/password", headers=headers, json={
            "old_password": "old-password-1", "new_password": "new-password-99",
        })
        assert changed.status_code == 200

        relogin = client.post("/api/auth/login", json={"username": username, "password": "new-password-99"})
        assert relogin.status_code == 200

        assert client.post("/api/auth/logout-all", headers=headers).status_code == 200
        assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_submit_requires_the_assigned_worker():
    from fastapi.testclient import TestClient

    from app.agent_simulator import CONTRACTS, build_contract_from_scenario
    from app.main import app

    with TestClient(app) as client:
        contract = build_contract_from_scenario("A")
        contract.state = "ACCEPTED"
        contract.hirer_id = "hirer-1"
        contract.worker_id = "worker-1"
        CONTRACTS[contract.id] = contract
        try:
            # hirer-1 is a party, so the route answers 403 (worker-only action)
            hirer_token = client.post("/api/auth/register", json={
                "username": f"h-{uuid.uuid4().hex[:8]}", "password": "longenough1",
            }).json()["token"]
            hirer_id = client.get("/api/auth/me", headers={
                "Authorization": f"Bearer {hirer_token}",
            }).json()["user"]["id"]
            CONTRACTS[contract.id].hirer_id = hirer_id

            hirer = client.post(f"/api/contracts/{contract.id}/submit", json={
                "artifact_type": "code", "code": "x = 1\n",
            }, headers={"Authorization": f"Bearer {hirer_token}"})
            assert hirer.status_code == 403
            assert "assigned worker" in hirer.json()["detail"]

            # a non-party gets the same 404 as an unknown contract
            outsider_token = client.post("/api/auth/register", json={
                "username": f"o-{uuid.uuid4().hex[:8]}", "password": "longenough1",
            }).json()["token"]
            outsider = client.post(f"/api/contracts/{contract.id}/submit", json={
                "artifact_type": "code", "code": "x = 1\n",
            }, headers={"Authorization": f"Bearer {outsider_token}"})
            assert outsider.status_code == 404
        finally:
            CONTRACTS.pop(contract.id, None)
