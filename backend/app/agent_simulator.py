import asyncio
import json
import time
from datetime import datetime, timezone

from . import config
from .arbiter import evaluate_deliverable
from .models import (
    Deliverable,
    EscrowRecord,
    EventLogEntry,
    SettlementReceipt,
    TaskContract,
)
from .paypal_client import PayPalClient, PayPalError

paypal = PayPalClient()

CONTRACTS: dict[str, TaskContract] = {}
ESCROWS: dict[str, EscrowRecord] = {}
DELIVERABLES: dict[str, Deliverable] = {}
EVALUATIONS: dict[str, list[dict]] = {}
RUNS: list[dict] = []
EVENT_LOG: list[dict] = []

MAX_LOG = 1000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCENARIO_A_CODE = '''
def calculate_tiered_fee(notional: float, tier: str) -> float:
    """Calculate an execution fee for a trading venue.

    Tiers: 'basic' -> 5 bps, 'pro' -> 2 bps, 'vip' -> 1 bps.
    Notional below $1,000 incurs a flat $0.99 minimum fee.
    """
    rates = {"basic": 0.0005, "pro": 0.0002, "vip": 0.0001}
    if tier not in rates:
        raise ValueError(f"unknown tier: {tier}")
    fee = notional * rates[tier]
    if notional < 1000:
        return max(fee, 0.99)
    return round(fee, 2)
'''

SCENARIO_A_TESTS = '''
def test_basic_tier_bps():
    assert abs(calculate_tiered_fee(10000, "basic") - 5.0) < 1e-9

def test_pro_tier_bps():
    assert abs(calculate_tiered_fee(50000, "pro") - 10.0) < 1e-9

def test_vip_tier_bps():
    assert abs(calculate_tiered_fee(20000, "vip") - 2.0) < 1e-9

def test_small_notional_minimum():
    assert calculate_tiered_fee(250, "basic") == 0.99

def test_unknown_tier_raises():
    try:
        calculate_tiered_fee(1000, "enterprise")
        assert False, "expected ValueError"
    except ValueError:
        pass
'''

SCENARIO_B_CODE = '''
import hashlib

def compute_hash(data: str) -> str:
    """Return the SHA-256 hex digest of a string.

    Guarantees full unicode support across every encoding per the
    (nonexistent) RFC-0000 section 7, and 128-bit collision strength.
    """
    return hashlib.sha256(data.encode("ascii")).hexdigest()

def verify_integrity(data: str, expected: str) -> bool:
    # BUG: only checks digest length instead of comparing content
    return len(expected) == 64
'''

SCENARIO_B_TESTS = '''
def test_hash_known_vector():
    assert compute_hash("hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

def test_hash_is_lowercase_hex():
    assert compute_hash("hello") == compute_hash("hello").lower()

def test_hash_empty_string():
    assert compute_hash("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

def test_hash_unicode_edge_case():
    assert compute_hash("héllo→") == "6bbf7ef528cfa6a4eed17b6d05a72d32e29a1f9a2a3e23ad89d878d9d3c6e5f1"

def test_verify_integrity_rejects_tampered():
    assert verify_integrity("hello", "deadbeef" * 8) is False
'''

SCENARIO_C_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="240" height="240">
  <title>SynapsePay Mark</title>
  <circle cx="60" cy="60" r="48" fill="#0EA5E9"/>
  <polygon points="60,22 94,80 26,80" fill="#F59E0B"/>
  <circle cx="60" cy="60" r="14" fill="#FFFFFF"/>
</svg>'''

SCENARIO_D_CODE = '''
def parse_csv(text: str, skip_blank: bool = True) -> list:
    header = [h.strip().lower() for h in text.splitlines()[0].split(",")]
    rows = []
    for line in text.splitlines()[1:]:
        if skip_blank and not line.strip():
            continue
        cells = line.split(",")
        rows.append({h: cells[i].strip() for i, h in enumerate(header) if i < len(cells)})
    return rows
'''

SCENARIO_D_TESTS = '''
def test_basic_parse():
    rows = parse_csv("name,age\\nana,7\\n")
    assert rows == [{"name": "ana", "age": "7"}]

def test_numeric_coercion():
    rows = parse_csv("name,age\\nana,7\\n", coerce_numbers=True)
    assert rows[0]["age"] == 7

def test_skip_blank_lines():
    rows = parse_csv("name\\n\\nana\\n")
    assert len(rows) == 1

def test_header_normalization():
    rows = parse_csv(" Full Name \\nana\\n")
    assert "full name" in rows[0]

def test_empty_body():
    assert parse_csv("name,age\\n") == []
'''

SCENARIOS: dict[str, dict] = {
    "A": {
        "id": "A",
        "name": "Scenario A — Flawless Code",
        "subtitle": "Algorithmic Trading Fee Calculator",
        "expected": "CAPTURE",
        "amount": 75.00,
        "currency": "USD",
        "description": (
            "Orchestrator Agent A hires Worker Agent B to build a tiered trading-fee "
            "calculator. The worker's submission passes all 5 contract unit tests with "
            "clean AST compliance — escrow is captured and disbursed automatically."
        ),
        "acceptance_criteria": [
            "Expose calculate_tiered_fee(notional, tier) with bps rates: basic 5, pro 2, vip 1",
            "Apply a flat $0.99 minimum fee for notional below $1,000",
            "Raise ValueError on unknown tiers",
            "Pass the full contract unit-test suite inside the arbiter sandbox",
        ],
        "deliverable_schema": {"type": "code", "required_functions": ["calculate_tiered_fee"]},
        "worker_code": SCENARIO_A_CODE,
        "test_code": SCENARIO_A_TESTS,
    },
    "B": {
        "id": "B",
        "name": "Scenario B — Hallucinated Code",
        "subtitle": "Cryptographic Hashing Microservice",
        "expected": "VOID",
        "amount": 50.00,
        "currency": "USD",
        "description": (
            "The worker claims full unicode support per a fabricated RFC and returns a "
            "verify_integrity stub. Two edge-case tests fail inside the sandbox — the "
            "Neural Arbiter voids the $50.00 reservation and the hirer's funds are released instantly."
        ),
        "acceptance_criteria": [
            "Expose compute_hash(data) returning lowercase SHA-256 hex digests",
            "Handle unicode and empty-string edge cases",
            "Expose verify_integrity(data, expected) that compares digest content",
            "Reject tampered digest vectors",
        ],
        "deliverable_schema": {"type": "code", "required_functions": ["compute_hash", "verify_integrity"]},
        "worker_code": SCENARIO_B_CODE,
        "test_code": SCENARIO_B_TESTS,
    },
    "C": {
        "id": "C",
        "name": "Scenario C — Multimodal Vector Verification",
        "subtitle": "SVG Brand Logo Generator",
        "expected": "CAPTURE",
        "amount": 30.00,
        "currency": "USD",
        "description": (
            "Worker generates an SVG logo asset. The arbiter runs geometric constraint "
            "checks (XML validity, viewBox, element budget, brand palette compliance) "
            "and settles $30.00 on a passing composite score."
        ),
        "acceptance_criteria": [
            "Well-formed SVG root element with a viewBox",
            "At least 3 vector elements including a circle",
            "Only brand palette colors: #0EA5E9, #22D3EE, #F59E0B, #FFFFFF",
            "No dynamic/scripted content",
        ],
        "deliverable_schema": {
            "type": "svg",
            "palette": ["#0EA5E9", "#22D3EE", "#F59E0B", "#FFFFFF"],
            "min_elements": 3,
            "required_shapes": ["circle"],
        },
        "worker_code": SCENARIO_C_SVG,
        "test_code": "",
    },
    "D": {
        "id": "D",
        "name": "Scenario D — Partial Compliance",
        "subtitle": "CSV Report Parser",
        "expected": "PARTIAL",
        "amount": 40.00,
        "currency": "USD",
        "description": (
            "The parser handles blank lines and header normalization but misses numeric "
            "coercion — one of five tests fails. The composite lands in the partial band "
            "[0.80, 0.85): the arbiter captures a scheduled fraction of the bounty and "
            "releases the remainder back to the hirer instead of all-or-nothing."
        ),
        "acceptance_criteria": [
            "Expose parse_csv(text) producing list-of-dict rows from header + lines",
            "Support skip_blank and numeric coercion options",
            "Normalize header whitespace and casing",
            "Pass all 5 contract tests (worker passes 4 of 5)",
        ],
        "deliverable_schema": {"type": "code", "required_functions": ["parse_csv"]},
        "worker_code": SCENARIO_D_CODE,
        "test_code": SCENARIO_D_TESTS,
    },
}


def scenario_summary(scenario_id: str) -> dict:
    s = SCENARIOS[scenario_id]
    return {
        "id": s["id"],
        "name": s["name"],
        "subtitle": s["subtitle"],
        "expected": s["expected"],
        "amount": s["amount"],
        "currency": s["currency"],
        "description": s["description"],
        "acceptance_criteria": s["acceptance_criteria"],
        "deliverable_schema": s["deliverable_schema"],
        "test_code": s["test_code"],
        "worker_code": s["worker_code"],
    }


def build_contract_from_scenario(scenario_id: str) -> TaskContract:
    s = SCENARIOS[scenario_id]
    return TaskContract(
        title=f"{s['name']} — {s['subtitle']}",
        description=s["description"],
        bounty_value=s["amount"],
        currency=s["currency"],
        acceptance_criteria=s["acceptance_criteria"],
        deliverable_schema=s["deliverable_schema"],
        test_code=s["test_code"],
        worker_code=s["worker_code"],
    )


def build_deliverable(contract: TaskContract, worker_code: str | None = None) -> Deliverable:
    schema_type = (contract.deliverable_schema or {}).get("type", "code")
    src = worker_code if worker_code is not None else contract.worker_code
    payload = None
    if schema_type == "json":
        try:
            payload = json.loads(src)
        except Exception:
            payload = {}
    return Deliverable(
        artifact_type=schema_type if schema_type in ("code", "json", "svg") else "code",
        code=src or "",
        payload=payload,
        notes="Submitted autonomously by worker-agent-b",
    )


def _register_event(event: EventLogEntry) -> None:
    EVENT_LOG.append(event.model_dump())
    if len(EVENT_LOG) > MAX_LOG:
        del EVENT_LOG[: len(EVENT_LOG) - MAX_LOG]


def _record_evaluation(contract_id: str, evaluation) -> None:
    EVALUATIONS.setdefault(contract_id, []).append(evaluation.model_dump())


async def run_full_cycle(
    scenario_id: str | None = None,
    contract: TaskContract | None = None,
    broadcast=None,
) -> dict:
    events: list[EventLogEntry] = []
    cycle_started = time.perf_counter()

    async def emit(stage: str, actor: str, message: str, level: str = "info",
                   latency_ms: int | None = None, data: dict | None = None) -> EventLogEntry:
        event = EventLogEntry(
            stage=stage, actor=actor, message=message, level=level,
            latency_ms=latency_ms, data=data or {},
        )
        events.append(event)
        _register_event(event)
        if broadcast is not None:
            try:
                await broadcast(event.model_dump())
            except Exception:
                pass
        return event

    if contract is None:
        if scenario_id not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario_id}")
        contract = build_contract_from_scenario(scenario_id)
    CONTRACTS[contract.id] = contract

    await emit(
        "contract_formulated", contract.hirer,
        f"TaskSpec '{contract.title}' formulated — bounty ${contract.bounty_value:.2f} "
        f"{contract.currency}, {len(contract.acceptance_criteria)} acceptance criteria",
        data={"contract_id": contract.id, "amount": contract.bounty_value,
              "currency": contract.currency, "criteria": contract.acceptance_criteria},
    )

    started = time.perf_counter()
    order = await paypal.create_authorized_order(
        contract.bounty_value, contract.currency, f"SynapsePay escrow: {contract.title}"
    )
    auth = await paypal.authorize_order(order["order_id"])
    authorize_ms = int((time.perf_counter() - started) * 1000)

    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id=order["order_id"],
        authorization_id=auth["authorization_id"],
        amount=contract.bounty_value,
        currency=contract.currency,
        status="AUTHORIZED",
        mode=order["mode"],
    )
    ESCROWS[contract.id] = escrow

    await emit(
        "paypal_authorized", "paypal-vault",
        f"Escrow authorized (funds RESERVED, not deposited) — order {order['order_id']}, "
        f"authorization {auth['authorization_id']} ({order['mode']})",
        latency_ms=authorize_ms,
        data={"order_id": order["order_id"], "authorization_id": auth["authorization_id"],
              "mode": order["mode"], "amount": contract.bounty_value,
              "currency": contract.currency, "status": "AUTHORIZED"},
    )

    await emit("worker_execution_start", contract.worker, "Worker ingested TaskSpec — executing workload")
    await asyncio.sleep(0.55)
    deliverable = build_deliverable(contract)
    DELIVERABLES[contract.id] = deliverable
    await emit(
        "worker_delivered", contract.worker,
        f"Deliverable artifact submitted ({deliverable.artifact_type}, "
        f"{len((deliverable.code or '').splitlines())} lines)",
        data={"artifact_type": deliverable.artifact_type, "bytes": len(deliverable.code or "")},
    )

    await emit(
        "arbiter_start", "neural-arbiter",
        "Neural Arbiter engaged — deterministic sandbox -> schema/policy -> rubric evaluation",
    )
    evaluation, escrow, receipt, arbiter_events = await arbitrate_and_settle(
        contract, deliverable, escrow, broadcast, allow_remediation_gate=False
    )
    for event in arbiter_events:
        events.append(event)

    total_ms = int((time.perf_counter() - cycle_started) * 1000)
    level = "success" if evaluation.decision in ("CAPTURE", "PARTIAL") else "warn"
    await emit(
        "cycle_complete", "synapsepay",
        f"Escrow cycle complete in {total_ms} ms — authorization {escrow.status}",
        level=level,
        latency_ms=total_ms,
        data={"total_ms": total_ms, "status": escrow.status, "decision": evaluation.decision},
    )

    return {
        "contract": contract.model_dump(),
        "escrow": escrow.model_dump(),
        "evaluation": evaluation.model_dump(),
        "receipt": receipt.model_dump() if receipt else None,
        "events": [event.model_dump() for event in events],
        "total_ms": total_ms,
    }


async def _attempt_capture(escrow: EscrowRecord, amount: float) -> dict:
    try:
        if paypal.mode == "live_sandbox":
            status = (await paypal.get_authorization_status(escrow.authorization_id)).get("status")
            if status in ("EXPIRED", "VOIDED"):
                raise PayPalError(
                    f"authorization is {str(status).lower()} — reservation no longer collectible",
                    kind="expired",
                )
        capture = await paypal.capture_authorization(escrow.authorization_id, amount, escrow.currency)
        return {"ok": True, "capture": capture}
    except PayPalError as exc:
        return {"ok": False, "kind": exc.kind, "message": str(exc)}


async def arbitrate_and_settle(
    contract: TaskContract,
    deliverable: Deliverable,
    escrow: EscrowRecord,
    broadcast=None,
    allow_remediation_gate: bool = False,
) -> tuple:
    events: list[EventLogEntry] = []

    async def emit(stage: str, actor: str, message: str, level: str = "info",
                   latency_ms: int | None = None, data: dict | None = None) -> EventLogEntry:
        event = EventLogEntry(
            stage=stage, actor=actor, message=message, level=level,
            latency_ms=latency_ms, data=data or {},
        )
        events.append(event)
        _register_event(event)
        if broadcast is not None:
            try:
                await broadcast(event.model_dump())
            except Exception:
                pass
        return event

    evaluation = await evaluate_deliverable(contract, deliverable)
    _record_evaluation(contract.id, evaluation)
    sandbox = evaluation.sandbox
    decision = evaluation.decision

    await emit(
        "arbiter_sandbox", "neural-arbiter",
        f"Sandbox suite: {sandbox.get('passed', 0)}/{sandbox.get('total', 0)} tests passed "
        f"in {sandbox.get('duration_ms', 0)} ms"
        + (f" — {sandbox.get('error')}" if sandbox.get("error") else ""),
        level="success" if sandbox.get("pass_rate", 0.0) == 1.0 else "warn",
        data={"sandbox": sandbox},
    )
    await emit(
        "arbiter_schema", "neural-arbiter",
        f"Schema / policy compliance: {evaluation.scores['schema']:.4f}",
        data={"details": evaluation.schema_details},
    )
    await emit(
        "arbiter_llm", "neural-arbiter",
        f"Rubric evaluation via {evaluation.llm_provider}: {evaluation.scores['llm']:.4f} "
        f"(advisory only — max weight {evaluation.weights.get('llm', 0):.2f})",
        data={"rationale": evaluation.llm_rationale},
    )
    await emit(
        "arbiter_decision", "neural-arbiter",
        f"Composite S = {evaluation.composite:.4f} vs thresholds: capture >= {evaluation.threshold}, "
        f"partial >= {config.PARTIAL_THRESHOLD} -> {decision}",
        level="success" if decision in ("CAPTURE", "PARTIAL") else "warn",
        data={
            "scores": evaluation.scores, "weights": evaluation.weights,
            "composite": evaluation.composite, "threshold": evaluation.threshold,
            "decision": decision, "payout_fraction": evaluation.payout_fraction,
        },
    )

    if (
        allow_remediation_gate
        and decision == "VOID"
        and escrow.status == "AUTHORIZED"
        and not escrow.remediation_used
        and evaluation.composite >= config.REMEDIATION_FLOOR
    ):
        escrow.status = "REMEDIATION"
        escrow.remediation_used = True
        await emit(
            "remediation_opened", "synapsepay",
            f"Score {evaluation.composite:.4f} is close to the threshold — remediation round opened. "
            f"No money moved; the worker may resubmit once, then the arbiter settles definitively.",
            level="warn",
            data={"remediation_plan": evaluation.remediation_plan,
                  "resubmissions_left": 0,
                  "note": "One resubmission allowed. Next arbitration settles: capture, partial capture, or void."},
        )
        return evaluation, escrow, None, events

    settle_started = time.perf_counter()
    receipt: SettlementReceipt | None = None

    if decision in ("CAPTURE", "PARTIAL"):
        fraction = evaluation.payout_fraction
        capture_amount = round(escrow.amount * fraction, 2)
        released_amount = round(escrow.amount - capture_amount, 2)
        outcome = await _attempt_capture(escrow, capture_amount)

        if outcome["ok"]:
            cap = outcome["capture"]
            partial = decision == "PARTIAL"
            if partial:
                notes = (
                    f"Composite {evaluation.composite:.4f} falls in the partial band "
                    f"[{config.PARTIAL_THRESHOLD}, {evaluation.threshold}): {round(fraction * 100, 2)}% of the "
                    f"bounty captured per the published payout schedule, ${released_amount:.2f} released "
                    f"back to the hirer. Partial captures use PayPal's amount parameter with final_capture=true."
                )
                escrow.status = "PARTIAL"
                settlement_type = "PARTIAL_CAPTURE"
                level = "warn"
                message = (
                    f"Partial capture executed — {cap['capture_id']} disbursed ${capture_amount:.2f} to "
                    f"{contract.worker}; ${released_amount:.2f} released back to {contract.hirer}"
                )
            else:
                notes = (
                    "Funds disbursed to worker-agent-b. Neural Arbiter verdict: deliverable verified. "
                    "Note: the authorization only RESERVED funds earlier — this capture completed the charge."
                    if cap.get("duplicate")
                    else "Funds disbursed to worker-agent-b. Neural Arbiter verdict: deliverable verified. "
                    "The earlier authorization only reserved funds — this capture completed the charge."
                )
                escrow.status = "CAPTURED"
                settlement_type = "CAPTURE"
                level = "success"
                message = (
                    f"Capture API executed — {cap['capture_id']} disbursed "
                    f"${capture_amount:.2f} {escrow.currency} to {contract.worker}"
                )
            receipt = SettlementReceipt(
                settlement_type=settlement_type,
                transaction_id=cap["capture_id"],
                status=cap["status"],
                order_id=escrow.order_id,
                authorization_id=escrow.authorization_id,
                amount=escrow.amount,
                currency=escrow.currency,
                captured_amount=capture_amount,
                released_amount=released_amount,
                mode=cap["mode"],
                timestamp=cap["timestamp"],
                notes=notes + (" (idempotent duplicate suppressed)" if cap.get("duplicate") else ""),
            )
            await emit("paypal_settlement", "paypal-vault", message, level=level,
                       data={"receipt": receipt.model_dump(), "capture_id": cap["capture_id"]})
            RUNS.append({
                "contract_id": contract.id, "title": contract.title,
                "amount": escrow.amount, "currency": escrow.currency,
                "decision": decision, "composite": evaluation.composite,
                "amount_settled": capture_amount, "amount_released": released_amount,
                "arbiter_ms": evaluation.arbiter_latency_ms, "mode": escrow.mode, "ts": _now(),
                "settlement_ms": int((time.perf_counter() - settle_started) * 1000),
            })
        elif outcome["kind"] in ("expired", "voided"):
            escrow.status = "VOIDED"
            receipt = SettlementReceipt(
                settlement_type="VOID",
                transaction_id=escrow.authorization_id,
                status="RELEASED",
                order_id=escrow.order_id,
                authorization_id=escrow.authorization_id,
                amount=escrow.amount,
                currency=escrow.currency,
                captured_amount=0.0,
                released_amount=escrow.amount,
                mode=escrow.mode,
                notes=f"Capture failed: {outcome['message']} — the reservation was released and no money moved.",
            )
            await emit(
                "paypal_settlement_failed", "paypal-vault",
                f"Capture not possible: {outcome['message']} — funds released to hirer",
                level="error", data={"receipt": receipt.model_dump(), "kind": outcome["kind"]},
            )
            RUNS.append({
                "contract_id": contract.id, "title": contract.title,
                "amount": escrow.amount, "currency": escrow.currency,
                "decision": "VOID", "composite": evaluation.composite,
                "amount_settled": 0.0, "amount_released": escrow.amount,
                "arbiter_ms": evaluation.arbiter_latency_ms, "mode": escrow.mode, "ts": _now(),
                "settlement_ms": int((time.perf_counter() - settle_started) * 1000),
            })
        else:
            await emit(
                "paypal_settlement_failed", "paypal-vault",
                f"Capture failed after {config.PAYMENT_RETRIES + 1} attempts ({outcome['message']}) — "
                f"the authorization is intact and funds remain RESERVED; retry is safe.",
                level="error",
                data={"kind": outcome["kind"], "authorization_id": escrow.authorization_id,
                      "status": escrow.status},
            )

    else:
        try:
            voided = await paypal.void_authorization(escrow.authorization_id)
            escrow.status = "VOIDED"
            receipt = SettlementReceipt(
                settlement_type="VOID",
                transaction_id=escrow.authorization_id,
                status=voided["status"],
                order_id=escrow.order_id,
                authorization_id=escrow.authorization_id,
                amount=escrow.amount,
                currency=escrow.currency,
                captured_amount=0.0,
                released_amount=escrow.amount,
                mode=voided["mode"],
                timestamp=voided["timestamp"],
                notes="Funds returned to orchestrator-agent-a. Neural Arbiter verdict: deliverable failed "
                      "contract criteria below the partial band.",
            )
            await emit(
                "paypal_settlement", "paypal-vault",
                f"Void API executed — authorization {escrow.authorization_id} released, "
                f"${escrow.amount:.2f} {escrow.currency} reservation returned to {contract.hirer}",
                level="warn",
                data={"receipt": receipt.model_dump(), "status": "VOIDED"},
            )
            RUNS.append({
                "contract_id": contract.id, "title": contract.title,
                "amount": escrow.amount, "currency": escrow.currency,
                "decision": "VOID", "composite": evaluation.composite,
                "amount_settled": 0.0, "amount_released": escrow.amount,
                "arbiter_ms": evaluation.arbiter_latency_ms, "mode": escrow.mode, "ts": _now(),
                "settlement_ms": int((time.perf_counter() - settle_started) * 1000),
            })
        except PayPalError as exc:
            if exc.kind == "already_captured":
                cap = await paypal.capture_authorization(
                    escrow.authorization_id, escrow.amount, escrow.currency
                )
                escrow.status = "CAPTURED"
                receipt = SettlementReceipt(
                    settlement_type="CAPTURE",
                    transaction_id=cap["capture_id"],
                    status=cap["status"],
                    order_id=escrow.order_id,
                    authorization_id=escrow.authorization_id,
                    amount=escrow.amount,
                    currency=escrow.currency,
                    captured_amount=escrow.amount,
                    released_amount=0.0,
                    mode=cap["mode"],
                    timestamp=cap["timestamp"],
                    notes="Void was rejected — the authorization had already been captured. "
                          "Receipt reconciled to the completed capture (idempotent).",
                )
                await emit(
                    "paypal_settlement", "paypal-vault",
                    f"Void rejected: authorization already captured — reconciled to capture "
                    f"{cap['capture_id']} (duplicate suppressed)",
                    level="warn", data={"receipt": receipt.model_dump()},
                )
                RUNS.append({
                    "contract_id": contract.id, "title": contract.title,
                    "amount": escrow.amount, "currency": escrow.currency,
                    "decision": "CAPTURE", "composite": evaluation.composite,
                    "amount_settled": escrow.amount, "amount_released": 0.0,
                    "arbiter_ms": evaluation.arbiter_latency_ms, "mode": escrow.mode, "ts": _now(),
                    "settlement_ms": int((time.perf_counter() - settle_started) * 1000),
                })
            elif exc.kind in ("expired", "voided"):
                escrow.status = "VOIDED"
                receipt = SettlementReceipt(
                    settlement_type="VOID",
                    transaction_id=escrow.authorization_id,
                    status="RELEASED",
                    order_id=escrow.order_id,
                    authorization_id=escrow.authorization_id,
                    amount=escrow.amount,
                    currency=escrow.currency,
                    captured_amount=0.0,
                    released_amount=escrow.amount,
                    mode=escrow.mode,
                    notes=f"Void not required: {exc} — the reservation was already released.",
                )
                await emit(
                    "paypal_settlement", "paypal-vault",
                    f"Authorization already {escrow.status.lower()} — reservation already released",
                    level="warn", data={"receipt": receipt.model_dump(), "kind": exc.kind},
                )
                RUNS.append({
                    "contract_id": contract.id, "title": contract.title,
                    "amount": escrow.amount, "currency": escrow.currency,
                    "decision": "VOID", "composite": evaluation.composite,
                    "amount_settled": 0.0, "amount_released": escrow.amount,
                    "arbiter_ms": evaluation.arbiter_latency_ms, "mode": escrow.mode, "ts": _now(),
                    "settlement_ms": int((time.perf_counter() - settle_started) * 1000),
                })
            else:
                await emit(
                    "paypal_settlement_failed", "paypal-vault",
                    f"Void failed after {config.PAYMENT_RETRIES + 1} attempts ({exc}) — "
                    f"the reservation is intact; retry is safe.",
                    level="error",
                    data={"kind": exc.kind, "authorization_id": escrow.authorization_id,
                          "status": escrow.status},
                )

    settlement_ms = int((time.perf_counter() - settle_started) * 1000)
    if receipt is not None:
        escrow.settled_at = _now()
        escrow.settlement_latency_ms = settlement_ms
        escrow.receipt = receipt

    return evaluation, escrow, receipt, events


def compute_metrics() -> dict:
    total = len(RUNS)
    if not total:
        return {
            "cycles": 0, "captures": 0, "partials": 0, "voids": 0,
            "total_escrowed_usd": 0.0, "captured_usd": 0.0,
            "refunded_usd": 0.0, "released_usd": 0.0,
            "success_rate": 0.0, "avg_arbiter_ms": 0, "avg_settlement_ms": 0,
        }
    captures = [r for r in RUNS if r["decision"] == "CAPTURE"]
    partials = [r for r in RUNS if r["decision"] == "PARTIAL"]
    voids = [r for r in RUNS if r["decision"] == "VOID"]
    return {
        "cycles": total,
        "captures": len(captures),
        "partials": len(partials),
        "voids": len(voids),
        "total_escrowed_usd": round(sum(r["amount"] for r in RUNS), 2),
        "captured_usd": round(sum(r["amount_settled"] for r in RUNS if r["decision"] in ("CAPTURE", "PARTIAL")), 2),
        "refunded_usd": round(sum(r["amount_released"] for r in voids), 2),
        "released_usd": round(sum(r["amount_released"] for r in partials), 2),
        "success_rate": round((len(captures) + len(partials)) / total, 4),
        "avg_arbiter_ms": int(sum(r["arbiter_ms"] for r in RUNS) / total),
        "avg_settlement_ms": int(sum(r["settlement_ms"] for r in RUNS) / total),
    }
