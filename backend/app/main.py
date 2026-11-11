import json
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .agent_simulator import (
    CONTRACTS,
    DELIVERABLES,
    ESCROWS,
    EVALUATIONS,
    SCENARIOS,
    compute_metrics,
    paypal,
    restore_from_disk,
    run_full_cycle,
    scenario_summary,
    sweep_expired,
)
from .arbiter import evaluate_deliverable
from .db import init as db_init
from .db import enabled as db_enabled
from .models import (
    ContractCreateRequest,
    Deliverable,
    EscrowRecord,
    ExecuteDemoRequest,
    SubmitDeliverableRequest,
    TaskContract,
    deadline_from_hours,
)
from .paypal_client import PayPalError

app_kwargs = {}
if not config.DOCS_ENABLED:
    app_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}


@asynccontextmanager
async def lifespan(_app):
    db_init(config.DATABASE_PATH)
    restore = restore_from_disk()
    swept = await sweep_expired()
    if swept or restore.get("restored"):
        print(
            f"[synapsepay] startup: persistence={'on' if db_enabled() else 'off'}, "
            f"restored={restore}, deadline-swept={len(swept)}"
        )
    yield
    from . import db

    db.close()


app = FastAPI(
    title="SynapsePay",
    description=(
        "Trust-minimized, AI-governed escrow for autonomous agent workflows. "
        "Escrow semantics: PayPal AUTHORIZE reserves (not deposits) funds; the Neural Arbiter's "
        "threshold rule - never the LLM alone - triggers capture, partial capture, or void. "
        "Operator-run arbiter; not permissionless."
    ),
    version=config.APP_VERSION,
    lifespan=lifespan,
    **app_kwargs,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=config.CORS_METHODS,
    allow_headers=config.CORS_HEADERS,
)


class RateLimitMiddleware:
    """In-memory sliding-window limiter: a first-line abuse brake, not a
    substitute for an edge gateway. Auth-backed limits are on the roadmap."""

    def __init__(self, app):
        self.app = app
        self._general: dict[str, deque] = {}
        self._arbitrate: dict[str, deque] = {}

    def _hit(self, bucket: dict, key: str, limit: int, now: float) -> bool:
        q = bucket.setdefault(key, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        ip = client[0] if client else "?"
        path = scope.get("path", "")
        now = time.time()
        if path.endswith("/arbitrate"):
            ok = self._hit(self._arbitrate, ip, config.RATE_LIMIT_ARBITRATE_PER_MINUTE, now)
            limit = config.RATE_LIMIT_ARBITRATE_PER_MINUTE
        else:
            ok = self._hit(self._general, ip, config.RATE_LIMIT_PER_MINUTE, now)
            limit = config.RATE_LIMIT_PER_MINUTE
        if not ok:
            response = JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded ({limit}/min) - slow down and retry."},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


app.add_middleware(RateLimitMiddleware)


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


def _validate_create(req: ContractCreateRequest) -> list[str]:
    errors = []
    if not (3 <= len(req.title.strip()) <= 120):
        errors.append("title must be 3-120 characters")
    if req.bounty_value <= 0 or req.bounty_value > config.BOUNTY_MAX:
        errors.append(f"bounty_value must be between 0 and {config.BOUNTY_MAX}")
    elif round(req.bounty_value, 2) != req.bounty_value:
        errors.append("bounty_value supports at most 2 decimal places")
    if req.currency not in config.CURRENCIES:
        errors.append(f"currency must be one of {sorted(config.CURRENCIES)}")
    if len(req.acceptance_criteria) > config.MAX_CRITERIA:
        errors.append(f"acceptance_criteria limited to {config.MAX_CRITERIA} lines")
    if len(req.worker_code) > config.MAX_CODE_CHARS:
        errors.append(f"worker_code limited to {config.MAX_CODE_CHARS} characters")
    if len(req.test_code) > config.MAX_CODE_CHARS:
        errors.append(f"test_code limited to {config.MAX_CODE_CHARS} characters")
    schema_type = (req.deliverable_schema or {}).get("type", "code")
    if schema_type == "code":
        test_count = len(re.findall(r"def\s+test_\w+", req.test_code or ""))
        if test_count < config.MIN_CONTRACT_TESTS:
            errors.append(
                f"code contracts need at least {config.MIN_CONTRACT_TESTS} unit tests "
                f"(found {test_count}) — one trivial test cannot earn a full score"
            )
    return errors


@app.get("/")
async def root() -> dict:
    return {"service": "SynapsePay", "version": config.APP_VERSION, "health": "/api/health"}


@app.get("/api/health")
async def health() -> dict:
    """Deliberately minimal: no thresholds or weights for submission-tuning."""
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": config.APP_VERSION,
        "paypal_mode": paypal.mode,
        "gemini_mode": config.GEMINI_MODE,
        "active_contracts": len(CONTRACTS),
        "persistence": "sqlite" if db_enabled() else "memory",
    }


@app.get("/api/config")
async def admin_config(token: str = "") -> dict:
    if not config.ADMIN_TOKEN:
        raise HTTPException(status_code=404, detail="not found")
    import hmac as hmac_mod

    if not hmac_mod.compare_digest(token, config.ADMIN_TOKEN):
        raise HTTPException(status_code=404, detail="not found")
    return {
        "arbiter_threshold": config.ARBITER_THRESHOLD,
        "partial_threshold": config.PARTIAL_THRESHOLD,
        "remediation_floor": config.REMEDIATION_FLOOR,
        "weights": {"tests": config.W_TESTS, "schema": config.W_SCHEMA, "llm": config.W_LLM},
        "llm_authority_note": "Gemini is advisory only: max composite weight 0.25 < capture threshold 0.85",
        "sandbox": {
            "backend": config.SANDBOX_BACKEND,
            "docker_available": None,
            "timeout_seconds": config.SANDBOX_TIMEOUT_SECONDS,
            "memory_mb": config.SANDBOX_MEMORY_MB,
            "security_note": config.SANDBOX_SECURITY_LEVEL,
        },
        "payment_retries": config.PAYMENT_RETRIES,
        "rate_limits": {
            "general_per_minute": config.RATE_LIMIT_PER_MINUTE,
            "arbitrate_per_minute": config.RATE_LIMIT_ARBITRATE_PER_MINUTE,
        },
        "persistence": {
            "backend": "sqlite" if db_enabled() else "memory",
            "path": config.DATABASE_PATH,
            "note": "SQLite survives restarts and hosting sleeps; Postgres is the roadmap step for multi-instance.",
        },
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
    errors = _validate_create(req)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    contract = TaskContract(
        title=req.title.strip(),
        description=req.description[:2000],
        bounty_value=req.bounty_value,
        currency=req.currency,
        acceptance_criteria=req.acceptance_criteria,
        deliverable_schema=req.deliverable_schema or {"type": "code", "required_functions": []},
        test_code=req.test_code,
        worker_code=req.worker_code,
        timeout_seconds=config.SANDBOX_TIMEOUT_SECONDS,
    )
    contract.arbiter_weights = {
        "tests": config.W_TESTS, "schema": config.W_SCHEMA, "llm": config.W_LLM,
    }
    contract.deadline_hours, contract.deadline_at = deadline_from_hours(
        req.deadline_hours, config.DEADLINE_HOURS_DEFAULT, config.DEADLINE_HOURS_MAX
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

    from . import db

    db.save_contract(contract.model_dump())
    db.save_escrow(escrow.model_dump())
    return {
        "contract": contract.model_dump(),
        "escrow": escrow.model_dump(),
        "order": order,
        "run_now": req.run_now,
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
    await sweep_expired()
    return {
        "contracts": [c.model_dump() for c in CONTRACTS.values()],
        "escrows": [e.model_dump() for e in ESCROWS.values()],
    }


@app.get("/api/contracts/{contract_id}")
async def get_contract(contract_id: str) -> dict:
    await sweep_expired()
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
    if escrow is not None and escrow.status not in ("AUTHORIZED", "REMEDIATION"):
        detail = "arbitration in progress" if escrow.status == "ARBITRATING" else f"contract already settled ({escrow.status})"
        raise HTTPException(status_code=409, detail=detail)
    if len(req.code or "") > config.MAX_CODE_CHARS:
        raise HTTPException(status_code=422, detail=f"code limited to {config.MAX_CODE_CHARS} characters")
    deliverable = Deliverable(
        artifact_type=req.artifact_type,
        code=req.code,
        payload=req.payload,
        notes=(req.notes or "Submitted via agent REST API")[:500],
    )
    DELIVERABLES[contract_id] = deliverable

    from . import db

    db.save_deliverable(contract_id, deliverable.model_dump())
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
        if escrow is not None and escrow.status == "ARBITRATING":
            raise HTTPException(status_code=409, detail="arbitration already in progress for this contract")
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


@app.post("/api/maintenance/sweep")
async def maintenance_sweep() -> dict:
    swept = await sweep_expired()
    return {"swept": swept, "count": len(swept)}


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
