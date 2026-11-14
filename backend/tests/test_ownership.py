import json as jsonlib
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import uuid
import websockets.sync.client
from websockets.exceptions import ConnectionClosed

sys.path.insert(0, r"C:\Users\Ananya\OneDrive\Desktop\SynapsePay (Agent Escrow)\backend")

from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.agent_simulator import CONTRACTS, USER_CONTRACTS, build_contract_from_scenario  # noqa: E402
from app.main import app  # noqa: E402
from app.ownership import event_visible_to  # noqa: E402
from app.state_machine import can_transition  # noqa: E402


@pytest.fixture()
def enforced_auth(monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_AUTH", True)


def _register(client, role, prefix="u"):
    username = f"{prefix}-{uuid.uuid4().hex[:8]}"
    res = client.post("/api/auth/register", json={
        "username": username, "password": "longenough1", "role": role,
    })
    assert res.status_code == 201
    token = res.json()["token"]
    user_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["user"]["id"]
    return username, {"Authorization": f"Bearer {token}"}, user_id


def _funded_contract(client, headers, title="ownership probe"):
    res = client.post("/api/contracts/create", headers=headers, json={
        "title": title,
        "bounty_value": 25.0,
        "test_code": (
            "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
            "def test_c():\n    assert True\n"
        ),
        "run_now": False,
    })
    assert res.status_code == 200, res.text
    return res.json()["contract"]


def test_third_user_gets_404_not_403_on_every_contract_route(enforced_auth):
    with TestClient(app) as client:
        hirer_name, hirer, hirer_id = _register(client, "hirer", "h")
        contract = _funded_contract(client, hirer)
        cid = contract["id"]

        _, worker, worker_id = _register(client, "worker", "w")
        acc = client.post(f"/api/contracts/{cid}/accept", json={}, headers=worker)
        assert acc.status_code == 200

        _, third, third_id = _register(client, "hirer", "t")
        routes = [
            ("GET", f"/api/contracts/{cid}"),
            ("GET", f"/api/contracts/{cid}/evaluations"),
            ("GET", f"/api/contracts/{cid}/submissions"),
            ("POST", f"/api/contracts/{cid}/submit"),
            ("POST", f"/api/contracts/{cid}/arbitrate"),
            ("POST", f"/api/contracts/{cid}/dispute"),
            ("POST", f"/api/contracts/{cid}/fund/start"),
            ("POST", f"/api/contracts/{cid}/fund/complete"),
            ("POST", f"/api/contracts/{cid}/reauthorize"),
            ("POST", f"/api/contracts/{cid}/cancel"),
        ]
        for method, path in routes:
            resp = client.request(method, path, headers=third,
                                  json={"order_id": "x"} if method == "POST" else None)
            assert resp.status_code == 404, f"{method} {path} -> {resp.status_code}: {resp.text[:100]}"
            assert resp.json()["detail"] == "not found", f"{method} {path} -> {resp.text[:100]}"

        demo = client.post("/api/contracts/execute-demo", json={"scenario_id": "A"}, headers=third)
        assert demo.status_code == 200, "scenario demos stay public"


def test_worker_cannot_fund_and_hirer_cannot_submit(enforced_auth):
    with TestClient(app) as client:
        hirer_name, hirer, hirer_id = _register(client, "hirer", "h")
        contract = _funded_contract(client, hirer)
        cid = contract["id"]

        _, worker, worker_id = _register(client, "worker", "w")

        pre = client.post(f"/api/contracts/{cid}/fund/start", headers=worker)
        assert pre.status_code == 404, "non-party gets no existence leak"

        acc = client.post(f"/api/contracts/{cid}/accept", json={}, headers=worker)
        assert acc.status_code == 200

        fund_attempt = client.post(f"/api/contracts/{cid}/fund/start", headers=worker)
        assert fund_attempt.status_code == 403
        assert "hirer" in fund_attempt.json()["detail"]

        hirer_submit = client.post(f"/api/contracts/{cid}/submit", json={
            "artifact_type": "code", "code": "x = 1\n",
        }, headers=hirer)
        assert hirer_submit.status_code == 403
        assert "assigned worker" in hirer_submit.json()["detail"]


def test_two_workers_racing_to_accept_yield_one_winner(enforced_auth):
    with TestClient(app) as client:
        hirer_name, hirer, hirer_id = _register(client, "hirer", "h")
        contract = _funded_contract(client, hirer)
        cid = contract["id"]

        _, w1, w1_id = _register(client, "worker", "w1")
        _, w2, w2_id = _register(client, "worker", "w2")

        results = {}

        def attempt(name, headers):
            results[name] = client.post(f"/api/contracts/{cid}/accept", json={}, headers=headers)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, "w1", w1), pool.submit(attempt, "w2", w2)]
            for f in futures:
                f.result()

        codes = sorted(r.status_code for r in results.values())
        assert codes == [200, 409], f"exactly one winner expected, got {codes}"
        assert CONTRACTS[cid].state == "ACCEPTED"


def test_lists_and_feeds_return_only_own_items(enforced_auth):
    with TestClient(app) as client:
        h1, h1h, h1_id = _register(client, "hirer", "h1")
        h2, h2h, h2_id = _register(client, "hirer", "h2")
        _funded_contract(client, h1h, "h1 contract")
        _funded_contract(client, h2h, "h2 contract")

        mine1 = client.get("/api/contracts", headers=h1h).json()["contracts"]
        mine2 = client.get("/api/contracts", headers=h2h).json()["contracts"]
        assert all(c["hirer_id"] == h1_id or c["worker_id"] == h1_id for c in mine1)
        assert all(c["hirer_id"] == h2_id or c["worker_id"] == h2_id for c in mine2)
        assert not any(c["hirer_id"] == h2_id for c in mine1)

        feed1 = client.get("/api/events/recent", headers=h1h).json()["events"]
        for e in feed1:
            cid = (e.get("data") or {}).get("contract_id")
            assert cid is None or any(c["id"] == cid for c in mine1)


def test_demo_contracts_are_ownerless_and_excluded_from_lists(enforced_auth):
    with TestClient(app) as client:
        hirer_name, hirer, hirer_id = _register(client, "hirer", "h")
        before = {c["id"] for c in client.get("/api/contracts", headers=hirer).json()["contracts"]}

        demo = client.post("/api/contracts/execute-demo", json={"scenario_id": "A"}, headers=hirer)
        assert demo.status_code == 200
        demo_cid = demo.json()["contract"]["id"]

        after_ids = {c["id"] for c in client.get("/api/contracts", headers=hirer).json()["contracts"]}
        assert demo_cid not in after_ids
        assert set(after_ids) == before


def test_401_for_unauthenticated_business_calls(enforced_auth):
    client = TestClient(app)
    resp = client.get("/api/contracts")
    assert resp.status_code == 401
    resp = client.post("/api/contracts/create", json={"title": "nope", "bounty_value": 5})
    assert resp.status_code == 401


def test_state_machine_allows_dispute_paths():
    assert can_transition("SUBMITTED", "DISPUTED")
    assert can_transition("DISPUTED", "SUBMITTED")
