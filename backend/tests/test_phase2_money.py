"""Phase 2: money correctness — no double authorizations, integer minor
units, deadline EXPIRED state, reconciliation drift flags, funding flow,
and stable idempotency keys."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import money
from app.agent_simulator import (
    CONTRACTS,
    ESCROWS,
    build_contract_from_scenario,
    build_deliverable,
    run_full_cycle,
    sweep_expired,
)
from app.lifecycle import (
    complete_funding,
    reconcile_escrows,
    reauthorize_escrow,
    start_funding,
)
from app.models import EscrowRecord
from app.paypal_client import PayPalClient


def test_no_double_authorization_when_reusing_contract():
    from app import agent_simulator as sim

    calls = {"orders": 0}
    original = sim.paypal.create_authorized_order

    async def counting_order(*args, **kwargs):
        calls["orders"] += 1
        return await original(*args, **kwargs)

    sim.paypal.create_authorized_order = counting_order
    try:
        contract = build_contract_from_scenario("A")
        escrow = EscrowRecord(
            contract_id=contract.id,
            order_id="ORD-KEEP-0001",
            authorization_id="AUTH-KEEP-0001",
            amount=75.0,
            status="AUTHORIZED",
            mode="simulated",
        )
        sim.CONTRACTS[contract.id] = contract
        sim.ESCROWS[contract.id] = escrow

        result = asyncio.run(run_full_cycle(contract=contract))
        assert result["evaluation"]["decision"] == "CAPTURE"
        assert sim.ESCROWS[contract.id].order_id == "ORD-KEEP-0001"
        assert sim.ESCROWS[contract.id].authorization_id == "AUTH-KEEP-0001"
        assert calls["orders"] == 0

        with pytest.raises(ValueError):
            asyncio.run(run_full_cycle(contract=contract)), "settled contracts cannot run a new cycle"
        assert calls["orders"] == 0
        assert sim.ESCROWS[contract.id].order_id == "ORD-KEEP-0001"
    finally:
        sim.paypal.create_authorized_order = original
        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)


def test_settled_contract_rejects_new_cycle():
    from app import agent_simulator as sim

    contract = build_contract_from_scenario("B")
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id="ORD-DONE",
        authorization_id="AUTH-DONE",
        amount=50.0,
        status="CAPTURED",
        mode="simulated",
    )
    sim.CONTRACTS[contract.id] = contract
    sim.ESCROWS[contract.id] = escrow
    try:
        with pytest.raises(ValueError):
            asyncio.run(run_full_cycle(contract=contract))
    finally:
        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)


def test_money_conversions_and_exact_splits():
    assert money.to_cents(75.0) == 7500
    assert money.to_cents(0.1 + 0.2) == 30
    assert money.to_cents("40.005") == 4001  # ROUND_HALF_UP at the boundary
    assert money.from_cents(1550) == 15.50
    assert money.paypal_amount(1550) == "15.50"

    captured, released = money.partial_split(4000, 0.3875)
    assert (captured, released) == (1550, 2450)
    assert captured + released == 4000

    for total in (1, 99, 1000, 12345):
        for fraction in (0.0, 0.25, 0.333, 0.5, 0.8125, 0.999, 1.0):
            captured, released = money.partial_split(total, fraction)
            assert captured + released == total
            assert 0 <= captured <= total


def test_partial_settlement_receipt_cents_sum_exactly():
    from app import agent_simulator as sim

    contract = build_contract_from_scenario("D")
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id="ORD-D",
        authorization_id="AUTH-D",
        amount=40.0,
        amount_cents=4000,
        status="AUTHORIZED",
        mode="simulated",
    )
    sim.CONTRACTS[contract.id] = contract
    sim.ESCROWS[contract.id] = escrow
    try:
        from app.arbiter import evaluate_deliverable
        from app.models import Deliverable

        from app.agent_simulator import arbitrate_and_settle

        evaluation, settled, receipt, _ = asyncio.run(
            arbitrate_and_settle(contract, build_deliverable(contract), escrow)
        )
        assert evaluation.decision == "PARTIAL"
        assert receipt.captured_cents + receipt.released_cents == receipt.amount_cents == 4000
        assert settled.status == "PARTIAL"
    finally:
        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)


def test_reauthorize_rotates_the_authorization():
    from app import agent_simulator as sim

    contract = build_contract_from_scenario("A")
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id="ORD-OLD",
        authorization_id="AUTH-OLD",
        amount=75.0,
        status="AUTHORIZED",
        mode="simulated",
    )
    sim.CONTRACTS[contract.id] = contract
    sim.ESCROWS[contract.id] = escrow
    try:
        updated = asyncio.run(reauthorize_escrow(contract, escrow))
        assert updated.authorization_id != "AUTH-OLD"
        assert updated.order_id != "ORD-OLD"
        assert updated.status == "AUTHORIZED"
        assert updated.last_error is None
        assert sim.paypal.sim_authorization_state("AUTH-OLD") == "VOIDED"
    finally:
        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)


def test_sweep_marks_contract_state_expired():
    from app import agent_simulator as sim

    contract = build_contract_from_scenario("A")
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id="ORD-EXP",
        authorization_id="AUTH-EXP",
        amount=75.0,
        status="AUTHORIZED",
        mode="simulated",
    )
    contract.deadline_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    sim.CONTRACTS[contract.id] = contract
    sim.ESCROWS[contract.id] = escrow
    try:
        swept = asyncio.run(sweep_expired())
        assert any(s["contract_id"] == contract.id for s in swept)
        assert escrow.status == "VOIDED"
        assert contract.state == "EXPIRED"
    finally:
        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)


def test_reconciliation_flags_simulated_capture_drift():
    from app import agent_simulator as sim

    contract = build_contract_from_scenario("C")
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id="ORD-DRIFT",
        authorization_id="AUTH-DRIFT",
        amount=30.0,
        status="AUTHORIZED",
        mode="simulated",
    )
    sim.CONTRACTS[contract.id] = contract
    sim.ESCROWS[contract.id] = escrow
    try:
        sim.paypal._sim_captures["AUTH-DRIFT"] = {
            "capture_id": "CAP-DRIFT", "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": "30.00"},
        }
        findings = asyncio.run(reconcile_escrows())
        match = [f for f in findings if f["contract_id"] == contract.id]
        assert match and match[0]["kind"] == "captured"
        assert escrow.status == "CAPTURED"
        assert "flagged for review" in (escrow.last_error or "")
    finally:
        sim.paypal._sim_captures.pop("AUTH-DRIFT", None)
        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)


def test_funding_flow_draft_to_funded():
    from app import agent_simulator as sim

    contract = build_contract_from_scenario("A")
    contract.state = "DRAFT"
    sim.CONTRACTS[contract.id] = contract
    try:
        started = asyncio.run(start_funding(contract))
        assert started["status"] == "DRAFT"
        assert sim.ESCROWS[contract.id].status == "DRAFT"

        escrow = asyncio.run(complete_funding(contract, started["order_id"]))
        assert escrow.status == "AUTHORIZED"
        assert escrow.authorization_id
        assert contract.state == "FUNDED"

        with pytest.raises(ValueError):
            asyncio.run(complete_funding(contract, started["order_id"]))
    finally:
        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)


def test_idempotency_keys_stable_per_intent():
    class FakeHTTP:
        def __init__(self):
            self.calls = []

        async def post(self, path, json=None, headers=None):
            self.calls.append({"path": path, "headers": headers})
            return httpx.Response(200, json={"id": "CAP-1", "status": "COMPLETED", "create_time": "now"})

    client = PayPalClient()
    fake = FakeHTTP()
    client._http = fake

    async def fake_token():
        return "tok"

    client.get_access_token = fake_token

    async def two_calls():
        await client._post_with_retry("/capture", None, idem_key="AUTH-1-capture")
        await client._post_with_retry("/capture", None, idem_key="AUTH-1-capture")

    asyncio.run(two_calls())

    assert len(fake.calls) == 2
    first, second = fake.calls
    assert first["headers"]["PayPal-Request-Id"] == "AUTH-1-capture"
    assert second["headers"]["PayPal-Request-Id"] == "AUTH-1-capture"
    assert first["headers"]["Idempotency-Key"] == second["headers"]["Idempotency-Key"]
