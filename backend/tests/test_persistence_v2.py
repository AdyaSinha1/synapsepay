"""Phase 1 persistence: SQLAlchemy-backed restart safety, atomic arbitration
claims, and centralized state-machine enforcement."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.agent_simulator import build_contract_from_scenario
from app.db import claim_arbitration
from app.models import EscrowRecord
from app.state_machine import can_transition, canonical, require_transition


def _escrow_row_data(contract, status="AUTHORIZED"):
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id=f"ORD-TEST-{contract.id}",
        authorization_id=f"AUTH-TEST-{contract.id}",
        amount=contract.bounty_value,
        status=status,
        mode="simulated",
    )
    return escrow, escrow.model_dump()


def test_restart_roundtrip_through_sqlalchemy(tmp_path):
    from app import agent_simulator as sim
    from app import db

    url = f"sqlite:///{(tmp_path / 'roundtrip.db').as_posix()}"
    assert db.init(url) is True
    try:
        contract = build_contract_from_scenario("A")
        escrow, escrow_data = _escrow_row_data(contract, status="CAPTURED")
        sim.CONTRACTS[contract.id] = contract
        sim.ESCROWS[contract.id] = escrow
        db.save_contract(contract.model_dump())
        db.save_escrow(escrow_data)

        sim.CONTRACTS.pop(contract.id, None)
        sim.ESCROWS.pop(contract.id, None)
        db.close()
        assert db.init(url) is True

        summary = sim.restore_from_disk()
        assert summary["restored"] is True
        assert contract.id in sim.CONTRACTS
        assert sim.ESCROWS[contract.id].status == "CAPTURED"

        data = db.load_all()
        assert any(c["id"] == contract.id for c in data["contracts"])
        assert any(e["contract_id"] == contract.id for e in data["escrows"])
    finally:
        db.close()


def test_concurrent_arbitration_claims_yield_exactly_one_winner(tmp_path):
    from app import db

    url = f"sqlite:///{(tmp_path / 'claims.db').as_posix()}"
    assert db.init(url) is True
    try:
        contract = build_contract_from_scenario("B")
        _escrow, escrow_data = _escrow_row_data(contract, status="AUTHORIZED")
        db.save_contract(contract.model_dump())
        db.save_escrow(escrow_data)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: claim_arbitration(contract.id), range(8)))

        assert sum(1 for won in results if won) == 1
        row_status = db.load_all()["escrows"][0]["status"]
        assert row_status == "ARBITRATING"

        assert claim_arbitration(contract.id) is False, "a settled/claimed escrow cannot be claimed again"
    finally:
        db.close()


def test_illegal_transitions_rejected_and_aliases_resolved():
    assert canonical("AUTHORIZED") == "FUNDED"
    assert canonical("CAPTURED") == "SETTLED"

    assert can_transition("AUTHORIZED", "ARBITRATING")
    assert can_transition("ARBITRATING", "CAPTURED")
    assert can_transition("ARBITRATING", "PARTIAL")
    assert can_transition("ARBITRATING", "REMEDIATION")
    assert can_transition("REMEDIATION", "ARBITRATING")

    with pytest.raises(ValueError):
        require_transition("VOIDED", "ARBITRATING")
    with pytest.raises(ValueError):
        require_transition("CAPTURED", "ARBITRATING")
    with pytest.raises(ValueError):
        require_transition("AUTHORIZED", "DRAFT")


def test_full_happy_path_transitions_are_legal():
    path = ["AUTHORIZED", "ARBITRATING", "CAPTURED"]
    for current, new in zip(path, path[1:]):
        require_transition(current, new)

    path = ["AUTHORIZED", "ARBITRATING", "VOIDED"]
    for current, new in zip(path, path[1:]):
        require_transition(current, new)

    path = ["AUTHORIZED", "ARBITRATING", "REMEDIATION", "ARBITRATING", "PARTIAL"]
    for current, new in zip(path, path[1:]):
        require_transition(current, new)
