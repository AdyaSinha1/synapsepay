import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .agent_simulator import (
    CONTRACTS,
    DELIVERABLES,
    ESCROWS,
    EVALUATIONS,
    SCENARIOS,
    compute_metrics,
    paypal,
    run_full_cycle,
    scenario_summary,
)
from .arbiter import evaluate_deliverable
from .models import (
    ContractCreateRequest,
    Deliverable,
    EscrowRecord,
    ExecuteDemoRequest,
    SubmitDeliverableRequest,
    TaskContract,
)
from .paypal_client import PayPalError

app = FastAPI(
    title="SynapsePay",
    description=(
        "Trustless, AI-governed escrow and settlement protocol for autonomous agent workflows. "
        "Escrow semantics: PayPal AUTHORIZE reserves (not deposits) funds; the Neural Arbiter's "
        "threshold rule - never the LLM alone - triggers capture, partial capture, or void."
    ),
    version=config.APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EventBus:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, event: dict) -> None:
        payload = json.dumps(event, default=str)
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


bus = EventBus()


@app.get("/")
async def root() -> dict:
    return {"service": "SynapsePay", "version": config.APP_VERSION, "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": config.APP_VERSION,
        "paypal_mode": paypal.mode,
        "gemini_mode": config.GEMINI_MODE,
        "gemini_model": config.GEMINI_MODEL,
        "arbiter_threshold": config.ARBITER_THRESHOLD,
        "partial_threshold": config.PARTIAL_THRESHOLD,
        "remediation_floor": config.REMEDIATION_FLOOR,
        "weights": {"tests": config.W_TESTS, "schema": config.W_SCHEMA, "llm": config.W_LLM},
        "llm_authority_note": "Gemini is advisory only: max composite weight 0.25 < capture threshold 0.85",
        "sandbox_security": config.SANDBOX_SECURITY_LEVEL,
        "payment_retries": config.PAYMENT_RETRIES,
        "active_contracts": len(CONTRACTS),
    }


@app.get("/api/scenarios")
async def scenarios() -> dict:
    return {"scenarios": [scenario_summary(sid) for sid in SCENARIOS]}


@app.get("/api/metrics")
async def metrics() -> dict:
    return compute_metrics()


@app.post("/api/contracts/create")
async def create_contract(req: ContractCreateRequest) -> dict:
    if req.bounty_value <= 0:
        raise HTTPException(status_code=422, detail="bounty_value must be positive")
    contract = TaskContract(
        title=req.title,
        description=req.description,
        bounty_value=req.bounty_value,
        currency=req.currency or "USD",
        acceptance_criteria=req.acceptance_criteria,
        deliverable_schema=req.deliverable_schema or {"type": "code", "required_functions": []},
        test_code=req.test_code,
        worker_code=req.worker_code,
    )
    try:
        order = await paypal.create_authorized_order(
            contract.bounty_value, contract.currency, f"SynapsePay escrow: {contract.title}"
        )
        auth = await paypal.authorize_order(order["order_id"])
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id=order["order_id"],
        authorization_id=auth["authorization_id"],
        amount=contract.bounty_value,
        currency=contract.currency,
        status="AUTHORIZED",
        mode=order["mode"],
    )
    CONTRACTS[contract.id] = contract
    ESCROWS[contract.id] = escrow
    return {
        "contract": contract.model_dump(),
        "escrow": escrow.model_dump(),
        "order": order,
        "semantics": "Authorization RESERVED the funds on the hirer's PayPal account; nothing is deposited until capture.",
    }


@app.post("/api/contracts/execute-demo")
async def execute_demo(req: ExecuteDemoRequest) -> dict:
    try:
        if req.contract_id:
            contract = CONTRACTS.get(req.contract_id)
            if contract is None:
                raise HTTPException(status_code=404, detail=f"unknown contract: {req.contract_id}")
            return await run_full_cycle(contract=contract, broadcast=bus.broadcast)
        if not req.scenario_id:
            raise HTTPException(status_code=422, detail="provide scenario_id or contract_id")
        if req.scenario_id not in SCENARIOS:
            raise HTTPException(status_code=404, detail=f"unknown scenario: {req.scenario_id}")
        return await run_full_cycle(scenario_id=req.scenario_id, broadcast=bus.broadcast)
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/contracts")
async def list_contracts() -> dict:
    return {
        "contracts": [c.model_dump() for c in CONTRACTS.values()],
        "escrows": [e.model_dump() for e in ESCROWS.values()],
    }


@app.get("/api/contracts/{contract_id}")
async def get_contract(contract_id: str) -> dict:
    contract = CONTRACTS.get(contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"unknown contract: {contract_id}")
    escrow = ESCROWS.get(contract_id)
    deliverable = DELIVERABLES.get(contract_id)
    return {
        "contract": contract.model_dump(),
        "escrow": escrow.model_dump() if escrow else None,
        "deliverable": deliverable.model_dump() if deliverable else None,
    }


@app.get("/api/contracts/{contract_id}/evaluations")
async def contract_evaluations(contract_id: str) -> dict:
    if contract_id not in CONTRACTS:
        raise HTTPException(status_code=404, detail=f"unknown contract: {contract_id}")
    return {
        "contract_id": contract_id,
        "evaluations": EVALUATIONS.get(contract_id, []),
        "audit_note": "Immutable evaluation records: test logs, schema checks, LLM rationale, scores, and decision for every arbitration round.",
    }


@app.post("/api/contracts/{contract_id}/submit")
async def submit_deliverable(contract_id: str, req: SubmitDeliverableRequest) -> dict:
    contract = CONTRACTS.get(contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"unknown contract: {contract_id}")
    escrow = ESCROWS.get(contract_id)
    if escrow is not None and escrow.status in ("CAPTURED", "PARTIAL", "VOIDED"):
        raise HTTPException(status_code=409, detail=f"contract already settled ({escrow.status})")
    deliverable = Deliverable(
        artifact_type=req.artifact_type,
        code=req.code,
        payload=req.payload,
        notes=req.notes or "Submitted via agent REST API",
    )
    DELIVERABLES[contract_id] = deliverable
    return {
        "contract_id": contract_id,
        "deliverable": deliverable.model_dump(),
        "status": "RECEIVED",
        "next": f"POST /api/contracts/{contract_id}/arbitrate",
    }


@app.post("/api/contracts/{contract_id}/arbitrate")
async def arbitrate_contract(contract_id: str) -> dict:
    contract = CONTRACTS.get(contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"unknown contract: {contract_id}")
    escrow = ESCROWS.get(contract_id)
    if escrow is None or escrow.status not in ("AUTHORIZED", "REMEDIATION"):
        raise HTTPException(status_code=409, detail="contract escrow is not active (already settled or missing)")
    deliverable = DELIVERABLES.get(contract_id)
    if deliverable is None:
        raise HTTPException(status_code=409, detail="no deliverable submitted yet for this contract")

    from .agent_simulator import arbitrate_and_settle

    evaluation, escrow, receipt, _events = await arbitrate_and_settle(
        contract, deliverable, escrow, bus.broadcast, allow_remediation_gate=True
    )
    return {
        "contract_id": contract_id,
        "evaluation": evaluation.model_dump(),
        "escrow": escrow.model_dump(),
        "receipt": receipt.model_dump() if receipt else None,
        "remediation": escrow.status == "REMEDIATION",
    }


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    bus.clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        bus.clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
