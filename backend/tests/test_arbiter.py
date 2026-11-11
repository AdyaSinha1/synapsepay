import asyncio

import httpx
import pytest

from app import config
from app.agent_simulator import (
    CONTRACTS,
    ESCROWS,
    EVALUATIONS,
    SCENARIOS,
    arbitrate_and_settle,
    build_contract_from_scenario,
    build_deliverable,
    compute_metrics,
)
from app.arbiter import (
    analyze_code_ast,
    check_json_payload,
    evaluate_deliverable,
    evaluate_svg_constraints,
    payout_fraction_for_score,
    run_code_sandbox,
)
from app.models import Deliverable, EscrowRecord, TaskContract
from app.paypal_client import PayPalClient, PayPalError, with_retries


def _run(coro):
    return asyncio.run(coro)


def _scenario_with_headroom(scenario_id: str) -> TaskContract:
    contract = build_contract_from_scenario(scenario_id)
    contract.timeout_seconds = 10.0
    return contract


def _fresh_escrow(contract: TaskContract, amount: float) -> EscrowRecord:
    return EscrowRecord(
        contract_id=contract.id,
        order_id=f"ORD-TEST-{contract.id}",
        authorization_id=f"AUTH-TEST-{contract.id}",
        amount=amount,
        status="AUTHORIZED",
        mode="simulated",
    )


def test_sandbox_all_pass():
    code = "def add(a, b):\n    return a + b\n"
    tests = (
        "def test_add_basic():\n    assert add(2, 3) == 5\n"
        "def test_add_negative():\n    assert add(-1, 1) == 0\n"
    )
    result = run_code_sandbox(code, tests)
    assert result["passed"] == 2
    assert result["total"] == 2
    assert result["pass_rate"] == 1.0
    assert result["error"] is None


def test_sandbox_counts_failures():
    code = "def add(a, b):\n    return a + b\n"
    tests = "def test_ok():\n    assert add(1, 1) == 2\ndef test_bad():\n    assert add(1, 1) == 3\n"
    result = run_code_sandbox(code, tests)
    assert result["passed"] == 1
    assert result["total"] == 2
    assert result["pass_rate"] == 0.5


def test_sandbox_timeout_kills_infinite_loop():
    result = run_code_sandbox(
        "while True:\n    pass\n", "def test_never():\n    assert False\n", timeout_seconds=1.0
    )
    assert result["passed"] == 0
    assert result["error"] is not None
    assert "timeout" in result["error"]


def test_forbidden_import_fails_schema():
    schema = {"type": "code", "required_functions": ["run"]}
    code = "import os\n\ndef run():\n    return os.getcwd()\n"
    score, details = analyze_code_ast(code, schema)
    assert score == 0.0
    assert any("forbidden" in d for d in details)


def test_dynamic_execution_banned():
    schema = {"type": "code", "required_functions": ["f"]}
    score, details = analyze_code_ast("def f():\n    return eval('1 + 1')\n", schema)
    assert score == 0.0
    assert any("dynamic execution" in d for d in details)


def test_required_function_missing():
    schema = {"type": "code", "required_functions": ["alpha", "beta"]}
    code = "def alpha():\n    return 1\n"
    score, details = analyze_code_ast(code, schema)
    assert score == 0.5
    assert any("beta" in d for d in details)


def test_json_payload_scoring():
    schema = {"required_fields": ["name", "value"], "field_types": {"value": "number"}}
    tests_score, schema_score, logs = check_json_payload({"name": "x", "value": 3}, schema)
    assert tests_score == 1.0
    assert schema_score == 1.0
    tests_score, schema_score, _ = check_json_payload({"name": None}, schema)
    assert tests_score == 0.0
    assert schema_score == 0.0


def test_svg_constraint_suite():
    schema = {"type": "svg", "palette": ["#0EA5E9", "#FFFFFF"], "min_elements": 2, "required_shapes": ["circle"]}
    good = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="#0EA5E9"/><rect width="2" height="2" fill="#FFFFFF"/></svg>'
    test_score, _total, _logs, schema_score = evaluate_svg_constraints(good, schema)
    assert test_score == 1.0
    assert schema_score == 1.0
    bad = '<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="#FF0000"/></svg>'
    test_score, _total, _logs, schema_score = evaluate_svg_constraints(bad, schema)
    assert test_score < 1.0
    assert schema_score < 1.0


def test_scenario_a_captures():
    contract = _scenario_with_headroom("A")
    evaluation = _run(evaluate_deliverable(contract, build_deliverable(contract)))
    assert evaluation.scores["tests"] == 1.0
    assert evaluation.scores["schema"] == 1.0
    assert evaluation.composite >= config.ARBITER_THRESHOLD
    assert evaluation.decision == "CAPTURE"
    assert evaluation.payout_fraction == 1.0


def test_scenario_b_voids():
    contract = _scenario_with_headroom("B")
    evaluation = _run(evaluate_deliverable(contract, build_deliverable(contract)))
    assert evaluation.scores["tests"] == 0.6
    assert evaluation.composite < config.PARTIAL_THRESHOLD
    assert evaluation.decision == "VOID"
    assert evaluation.payout_fraction == 0.0


def test_scenario_d_partial_capture():
    contract = _scenario_with_headroom("D")
    evaluation = _run(evaluate_deliverable(contract, build_deliverable(contract)))
    assert config.PARTIAL_THRESHOLD <= evaluation.composite < config.ARBITER_THRESHOLD
    assert evaluation.decision == "PARTIAL"
    assert evaluation.remediation_plan, "failed tests must produce a remediation plan"
    assert abs(evaluation.payout_fraction - 0.3875) < 0.001


def test_composite_math_matches_weights():
    contract = _scenario_with_headroom("A")
    evaluation = _run(evaluate_deliverable(contract, build_deliverable(contract)))
    expected = (
        evaluation.weights["tests"] * evaluation.scores["tests"]
        + evaluation.weights["schema"] * evaluation.scores["schema"]
        + evaluation.weights["llm"] * evaluation.scores["llm"]
    )
    assert abs(evaluation.composite - round(expected, 4)) < 1e-6


def test_llm_cannot_authorize_alone():
    assert config.W_LLM < config.ARBITER_THRESHOLD
    contract = TaskContract(
        title="adversarial",
        bounty_value=10.0,
        test_code="def test_x():\n    assert False\n",
        deliverable_schema={"type": "code", "required_functions": ["missing_fn"]},
        worker_code="import os\n\nx = 1\n",
    )
    evaluation = _run(evaluate_deliverable(contract, Deliverable(artifact_type="code", code=contract.worker_code)))
    assert evaluation.scores["tests"] == 0.0
    assert evaluation.scores["schema"] == 0.0
    assert evaluation.composite <= config.W_LLM
    assert evaluation.decision == "VOID"


def test_partial_payout_schedule():
    assert payout_fraction_for_score(0.86) == 1.0
    assert payout_fraction_for_score(0.75) == 0.0
    assert payout_fraction_for_score(0.80) == 0.25
    assert abs(payout_fraction_for_score(0.8125) - 0.3875) < 1e-9
    assert payout_fraction_for_score(0.8499) <= 0.80


def test_remediation_gate_opens_then_settles():
    contract = _scenario_with_headroom("B")
    CONTRACTS[contract.id] = contract
    escrow = _fresh_escrow(contract, 50.0)
    evaluation1, escrow1, receipt1, _ = _run(
        arbitrate_and_settle(contract, build_deliverable(contract), escrow, allow_remediation_gate=True)
    )
    assert evaluation1.decision == "VOID"
    assert escrow1.status == "REMEDIATION"
    assert escrow1.remediation_used is True
    assert receipt1 is None
    assert len(EVALUATIONS[contract.id]) == 1

    evaluation2, escrow2, receipt2, _ = _run(
        arbitrate_and_settle(contract, build_deliverable(contract), escrow1, allow_remediation_gate=True)
    )
    assert escrow2.status == "VOIDED"
    assert receipt2 is not None and receipt2.settlement_type == "VOID"
    assert len(EVALUATIONS[contract.id]) == 2


def test_demo_cycle_scenarios_settle_without_remediation():
    contract = _scenario_with_headroom("B")
    escrow = _fresh_escrow(contract, 50.0)
    evaluation, settled, receipt, _ = _run(
        arbitrate_and_settle(contract, build_deliverable(contract), escrow, allow_remediation_gate=False)
    )
    assert evaluation.decision == "VOID"
    assert settled.status == "VOIDED"
    assert receipt is not None


def test_evaluation_audit_trail():
    contract = _scenario_with_headroom("A")
    CONTRACTS[contract.id] = contract
    escrow = _fresh_escrow(contract, 75.0)
    _evaluation, settled, receipt, _ = _run(
        arbitrate_and_settle(contract, build_deliverable(contract), escrow)
    )
    assert receipt is not None and receipt.settlement_type == "CAPTURE"
    assert settled.status == "CAPTURED"
    records = EVALUATIONS[contract.id]
    assert len(records) == 1
    assert records[0]["test_logs"]
    assert records[0]["decision"] == "CAPTURE"


def test_partial_settlement_receipt_amounts():
    contract = _scenario_with_headroom("D")
    escrow = _fresh_escrow(contract, 40.0)
    _evaluation, settled, receipt, _ = _run(
        arbitrate_and_settle(contract, build_deliverable(contract), escrow)
    )
    assert settled.status == "PARTIAL"
    assert receipt.settlement_type == "PARTIAL_CAPTURE"
    assert abs(receipt.captured_amount - 15.50) < 0.01
    assert abs(receipt.released_amount - 24.50) < 0.01
    assert receipt.captured_amount + receipt.released_amount == receipt.amount


def test_metrics_include_partials():
    metrics = compute_metrics()
    assert {"cycles", "captures", "partials", "voids", "captured_usd", "refunded_usd", "released_usd"} <= set(metrics)


def test_retry_helper_recovers_from_transient_errors():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom")
        return "ok"

    assert _run(with_retries(flaky, retries=3, base_delay=0.001)) == "ok"
    assert calls["n"] == 3


def test_retry_helper_gives_up_eventually():
    async def always_fails():
        raise httpx.ConnectError("down")

    with pytest.raises(PayPalError):
        _run(with_retries(always_fails, retries=1, base_delay=0.001))


def test_paypal_mock_lifecycle():
    client = PayPalClient()
    if client.mode != "simulated":
        pytest.skip("real PayPal credentials configured; skipping mock assertions")

    async def flow():
        order = await client.create_authorized_order(75.0)
        auth = await client.authorize_order(order["order_id"])
        capture = await client.capture_authorization(auth["authorization_id"], 75.0)
        order2 = await client.create_authorized_order(10.0)
        auth2 = await client.authorize_order(order2["order_id"])
        void = await client.void_authorization(auth2["authorization_id"])
        return order, auth, capture, void

    order, auth, capture, void = _run(flow())
    assert order["order_id"].startswith("ORD-SIM-")
    assert auth["authorization_id"].startswith("AUTH-SIM-")
    assert capture["capture_id"].startswith("CAP-SIM-")
    assert capture["status"] == "COMPLETED"
    assert void["status"] == "VOIDED"


def test_simulated_capture_is_idempotent_and_void_conflicts():
    client = PayPalClient()
    if client.mode != "simulated":
        pytest.skip("real PayPal credentials configured; skipping mock assertions")

    async def flow():
        order = await client.create_authorized_order(40.0)
        auth = await client.authorize_order(order["order_id"])
        first = await client.capture_authorization(auth["authorization_id"], 15.5)
        second = await client.capture_authorization(auth["authorization_id"], 15.5)
        return first, second, auth

    first, second, auth = _run(flow())
    assert first["capture_id"] == second["capture_id"]
    assert second.get("duplicate") is True

    async def conflicting_void():
        await client.void_authorization(auth["authorization_id"])

    with pytest.raises(PayPalError) as excinfo:
        _run(conflicting_void())
    assert excinfo.value.kind == "already_captured"


def test_weights_sum_to_one_by_default():
    contract = _scenario_with_headroom("A")
    assert abs(sum(contract.arbiter_weights.values()) - 1.0) < 1e-9


def test_heuristic_rubric_is_bounded():
    from app.arbiter import heuristic_rubric

    contract = TaskContract(title="t", bounty_value=1.0, deliverable_schema={"type": "code"})
    empty = heuristic_rubric(contract, Deliverable(artifact_type="code", code="x = 1"))
    rich = heuristic_rubric(
        contract,
        Deliverable(
            artifact_type="code",
            code='def f(x: int) -> int:\n    """Doc."""\n    try:\n        return x\n    except Exception:\n        raise\n' * 4,
        ),
    )
    assert 0.30 <= empty[0] <= 0.75
    assert 0.30 <= rich[0] <= 0.75
    assert rich[0] > empty[0]


def test_lint_flags_getattr_builtins_bypass():
    schema = {"type": "code", "required_functions": ["f"]}
    exploit = "def f():\n    return getattr(__builtins__, 'ev' + 'al')('1 + 1')\n"
    score, details = analyze_code_ast(exploit, schema)
    assert score == 0.0
    assert any("policy violation" in d for d in details)


def test_lint_flags_dunder_attribute_access():
    schema = {"type": "code", "required_functions": ["f"]}
    code = "def f(obj):\n    return obj.__subclasses__()\n"
    score, details = analyze_code_ast(code, schema)
    assert score == 0.0
    assert any("__subclasses__" in d for d in details)


def test_single_trivial_test_gets_coverage_factor():
    from app.arbiter import evaluate_deliverable

    contract = TaskContract(
        title="t",
        bounty_value=10.0,
        timeout_seconds=10.0,
        test_code="def test_ok():\n    assert add(1, 1) == 2\n",
        deliverable_schema={"type": "code"},
        worker_code="def add(a, b):\n    return a + b\n",
    )
    evaluation = _run(evaluate_deliverable(contract, Deliverable(artifact_type="code", code=contract.worker_code)))
    assert evaluation.scores["tests"] == round(1 / 3, 4)
    assert any("coverage factor" in d for d in evaluation.schema_details)
    assert evaluation.decision == "VOID"


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_health_is_minimal_and_admin_config_is_hidden():
    client = _client()
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert "arbiter_threshold" not in health
    assert "weights" not in health
    assert client.get("/api/config", params={"token": "x"}).status_code == 404


def test_create_locks_arbiter_weights_and_validates_inputs():
    client = _client()
    tests = (
        "def test_a():\n    assert slug('a b') == 'a-b'\n"
        "def test_b():\n    assert slug('A  B') == 'a-b'\n"
        "def test_c():\n    assert slug('x-y') == 'x-y'\n"
    )
    ok = client.post("/api/contracts/create", json={
        "title": "Weight lock probe",
        "bounty_value": 10.0,
        "currency": "USD",
        "deliverable_schema": {"type": "code", "required_functions": ["slug"]},
        "test_code": tests,
        "worker_code": "def slug(s):\n    return '-'.join(s.lower().split())\n",
        "arbiter_weights": {"tests": 0.0, "schema": 0.0, "llm": 1.0},
    })
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["contract"]["arbiter_weights"] == {
        "tests": config.W_TESTS, "schema": config.W_SCHEMA, "llm": config.W_LLM,
    }
    assert body["contract"]["deadline_at"] is not None

    assert client.post("/api/contracts/create", json={"title": "ab", "bounty_value": 10.0}).status_code == 422
    assert client.post("/api/contracts/create", json={"title": "ok title", "bounty_value": 99999.0}).status_code == 422
    assert client.post("/api/contracts/create", json={"title": "ok title", "bounty_value": 10.999}).status_code == 422
    assert client.post("/api/contracts/create", json={"title": "ok title", "bounty_value": 10.0, "currency": "BTC"}).status_code == 422
    too_few = {"title": "ok title", "bounty_value": 10.0, "deliverable_schema": {"type": "code"},
               "test_code": "def test_one():\n    assert True\n"}
    assert client.post("/api/contracts/create", json=too_few).status_code == 422
    oversized = dict(too_few, test_code="def test_a():\n    assert True\ndef test_b():\n    assert True\ndef test_c():\n    assert True\n", worker_code="x = 1\n" * 20001)
    assert client.post("/api/contracts/create", json=oversized).status_code == 422


def test_void_vs_already_captured_is_flagged_not_paid():
    from app.agent_simulator import paypal as shared_paypal, RUNS

    contract = build_contract_from_scenario("B")
    escrow = _fresh_escrow(contract, 50.0)

    async def pre_capture():
        await shared_paypal.capture_authorization(escrow.authorization_id, 50.0)

    _run(pre_capture())
    evaluation, settled, receipt, _ = _run(
        arbitrate_and_settle(contract, build_deliverable(contract), escrow)
    )
    assert evaluation.decision == "VOID"
    assert settled.status == "CAPTURED"
    assert receipt.needs_review is True
    assert RUNS[-1]["decision"] == "NEEDS_REVIEW"


def test_deadline_sweep_auto_voids_expired_escrows():
    from datetime import datetime as dt, timedelta as td, timezone as tz

    from app.agent_simulator import ESCROWS, sweep_expired

    contract = build_contract_from_scenario("A")
    escrow = _fresh_escrow(contract, 75.0)
    contract.deadline_at = (dt.now(tz.utc) - td(hours=1)).isoformat()
    CONTRACTS[contract.id] = contract
    ESCROWS[contract.id] = escrow

    swept = _run(sweep_expired())
    assert any(s["contract_id"] == contract.id for s in swept)
    assert escrow.status == "VOIDED"
    assert escrow.receipt.notes.startswith("Auto-voided by the deadline sweep")


def test_submit_blocked_while_arbitrating():
    client = _client()
    contract = build_contract_from_scenario("B")
    escrow = _fresh_escrow(contract, 50.0)
    escrow.status = "ARBITRATING"
    CONTRACTS[contract.id] = contract
    ESCROWS[contract.id] = escrow
    resp = client.post(f"/api/contracts/{contract.id}/submit", json={"artifact_type": "code", "code": "x = 1\n"})
    assert resp.status_code == 409
    assert "arbitration" in resp.json()["detail"]
