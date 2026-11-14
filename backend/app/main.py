import asyncio
import contextlib
import json
import logging
import re
import time
import traceback
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from . import money
from .agent_simulator import (
    CONTRACTS,
    DELIVERABLES,
    ESCROWS,
    EVALUATIONS,
    EVENT_LOG,
    SCENARIOS,
    compute_metrics,
    paypal,
    register_contract_party,
    restore_from_disk,
    run_full_cycle,
    scenario_summary,
    sweep_expired,
)
from .arbiter import evaluate_deliverable, run_code_sandbox
from .auth import require_user, router as auth_router
from .db import init as db_init
from .db import enabled as db_enabled
from .lifecycle import (
    complete_funding,
    reconcile_escrows,
    reauthorization_recommended,
    reauthorize_escrow,
    start_funding,
)
from .ownership import party_or_404, require_role, visible_contract_ids, event_visible_to
from .models import (
    AcceptRequest,
    ContractCreateRequest,
    Deliverable,
    DisputeRequest,
    DisputeResolveRequest,
    EscrowRecord,
    ExecuteDemoRequest,
    FundCompleteRequest,
    SandboxPreviewRequest,
    SubmitDeliverableRequest,
    TaskContract,
    deadline_from_hours,
)
from .paypal_client import PayPalError
from .obs import RequestLoggingMiddleware, SecurityHeadersMiddleware

logger = logging.getLogger("synapsepay")
logging.basicConfig(level=logging.INFO, format="%(message)s")

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
    stop_event = asyncio.Event()

    async def periodic_jobs():
        while not stop_event.is_set():
            try:
                await sweep_expired()
                await reconcile_escrows()
            except Exception:
                pass
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=60)

    jobs_task = asyncio.create_task(periodic_jobs())
    yield
    stop_event.set()
    with contextlib.suppress(asyncio.CancelledError):
        await jobs_task
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
app.include_router(auth_router)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)


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
        self.clients: set[tuple[WebSocket, str]] = set()

    async def broadcast(self, event: dict) -> None:
        from .ownership import event_visible_to
        from .agent_simulator import USER_CONTRACTS

        payload = json.dumps(event, default=str)
        dead: list[tuple[WebSocket, str]] = []
        for client in list(self.clients):
            ws, user_id = client
            contract_ids = USER_CONTRACTS.get(user_id, set())
            if not event_visible_to(event, contract_ids):
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            self.clients.discard(client)


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


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """No stack traces to clients: full detail goes to the server log, the
    response carries only a request id for correlation."""
    request_id = getattr(request.state, "request_id", "")
    logger.error(json.dumps({
        "level": "error",
        "request_id": request_id,
        "path": request.url.path,
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc(limit=6),
    }))
    return JSONResponse(status_code=500, content={"detail": "internal server error", "request_id": request_id})


@app.get("/")
async def root() -> dict:
    return {"service": "SynapsePay", "version": config.APP_VERSION, "health": "/api/health"}


@app.get("/api/health")
async def health() -> dict:
    """Deliberately minimal: no thresholds or weights for submission-tuning."""
    from .arbiter import docker_available

    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": config.APP_VERSION,
        "paypal_mode": paypal.mode,
        "gemini_mode": config.GEMINI_MODE,
        "active_contracts": len(CONTRACTS),
        "persistence": "sqlite" if db_enabled() else "memory",
        "storage": "postgres" if config.DATABASE_URL.strip() else "ephemeral",
        "sandbox": {
            "backend": "docker" if docker_available() else "native",
            "docker_available": docker_available(),
            "note": "containers are the security boundary; the AST policy scan is a lint",
        },
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


def _enforce_open_contract_cap(user) -> None:
    """Per-user cap on open contracts when signed in; a global cap otherwise."""
    open_states = ("DRAFT", "FUNDED", "ACCEPTED", "SUBMITTED", "ARBITRATING", "REMEDIATION")
    if user is not None:
        owned_open = sum(
            1 for c in CONTRACTS.values()
            if c.owner_id == user.id and c.state in open_states
        )
        if owned_open >= config.OPEN_CONTRACT_CAP:
            raise HTTPException(
                status_code=429,
                detail=f"open-contract cap reached ({config.OPEN_CONTRACT_CAP}) — settle, cancel or expire a contract first",
            )
    else:
        total_open = sum(1 for e in ESCROWS.values() if e.status in open_states)
        if total_open >= config.OPEN_CONTRACT_CAP * 4:
            raise HTTPException(status_code=429, detail="server demo capacity reached — try again later")


@app.post("/api/contracts/create")
async def create_contract(req: ContractCreateRequest, user=Depends(require_user)) -> dict:
    errors = _validate_create(req)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    _enforce_open_contract_cap(user)
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
        owner_id=(user.id if user else ""),
        hirer_id=(user.id if user else ""),
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
        amount_cents=money.to_cents(contract.bounty_value),
        status="AUTHORIZED",
        mode=order["mode"],
    )
    CONTRACTS[contract.id] = contract
    ESCROWS[contract.id] = escrow
    if user is not None:
        register_contract_party(user.id, contract.id)

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
async def execute_demo(req: ExecuteDemoRequest, user=Depends(require_user)) -> dict:
    try:
        if req.contract_id:
            if user is None:
                raise HTTPException(status_code=401, detail="authentication required to run a specific contract")
            party_or_404(req.contract_id, user)
            require_role(user, CONTRACTS[req.contract_id], "hirer", "re-run this contract")
            contract = CONTRACTS.get(req.contract_id)
            return await run_full_cycle(contract=contract, broadcast=bus.broadcast)
        if not req.scenario_id:
            raise HTTPException(status_code=422, detail="provide scenario_id or contract_id")
        if req.scenario_id not in SCENARIOS:
            raise HTTPException(status_code=404, detail=f"unknown scenario: {req.scenario_id}")
        return await run_full_cycle(scenario_id=req.scenario_id, broadcast=bus.broadcast)
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/contracts")
async def list_contracts(user=Depends(require_user)) -> dict:
    await sweep_expired()
    visible = visible_contract_ids(user)
    return {
        "contracts": [c.model_dump() for c in CONTRACTS.values() if c.id in visible],
        "escrows": [e.model_dump() for e in ESCROWS.values() if e.contract_id in visible],
    }


@app.get("/api/contracts/{contract_id}")
async def get_contract(contract_id: str, user=Depends(require_user)) -> dict:
    await sweep_expired()
    contract = party_or_404(contract_id, user)
    escrow = ESCROWS.get(contract_id)
    deliverable = DELIVERABLES.get(contract_id)
    return {
        "contract": contract.model_dump(),
        "escrow": escrow.model_dump() if escrow else None,
        "deliverable": deliverable.model_dump() if deliverable else None,
    }


@app.get("/api/contracts/{contract_id}/evaluations")
async def contract_evaluations(contract_id: str, user=Depends(require_user)) -> dict:
    party_or_404(contract_id, user)
    return {
        "contract_id": contract_id,
        "evaluations": EVALUATIONS.get(contract_id, []),
        "audit_note": "Immutable evaluation records: test logs, schema checks, LLM rationale, scores, and decision for every arbitration round.",
    }


@app.post("/api/contracts/{contract_id}/submit")
async def submit_deliverable(contract_id: str, req: SubmitDeliverableRequest, user=Depends(require_user)) -> dict:
    contract = party_or_404(contract_id, user)
    require_role(user, contract, "worker", "submit deliverables")
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
    if contract.state in ("FUNDED", "ACCEPTED"):
        from .state_machine import require_transition

        require_transition(contract.state, "SUBMITTED")
        contract.state = "SUBMITTED"
        db.save_contract(contract.model_dump())
    return {
        "contract_id": contract_id,
        "deliverable": deliverable.model_dump(),
        "status": "RECEIVED",
        "next": f"POST /api/contracts/{contract_id}/arbitrate",
    }


@app.post("/api/contracts/{contract_id}/arbitrate")
async def arbitrate_contract(contract_id: str, user=Depends(require_user)) -> dict:
    contract = party_or_404(contract_id, user)
    escrow = ESCROWS.get(contract_id)
    if escrow is None or escrow.status not in ("AUTHORIZED", "REMEDIATION"):
        if escrow is not None and escrow.status == "ARBITRATING":
            raise HTTPException(status_code=409, detail="arbitration already in progress for this contract")
        raise HTTPException(status_code=409, detail="contract escrow is not active (already settled or missing)")
    if contract.state not in ("FUNDED", "ACCEPTED", "SUBMITTED"):
        if contract.state == "DISPUTED":
            raise HTTPException(status_code=409, detail="contract is in dispute — arbitration frozen pending review")
        raise HTTPException(status_code=409, detail=f"contract state is {contract.state}, not arbitratable")

    from .terms import terms_hash_of

    if contract.terms_hash and terms_hash_of(contract) != contract.terms_hash:
        raise HTTPException(
            status_code=409,
            detail="arbitration terms are locked: tests, criteria or weights changed after funding",
        )
    deliverable = DELIVERABLES.get(contract_id)
    if deliverable is None:
        raise HTTPException(status_code=409, detail="no deliverable submitted yet for this contract")

    from .agent_simulator import arbitrate_and_settle

    evaluation, escrow, receipt, _events = await arbitrate_and_settle(
        contract, deliverable, escrow, bus.broadcast, allow_remediation_gate=True
    )
    if evaluation is None:
        raise HTTPException(status_code=409, detail="arbitration already in progress for this contract")
    return {
        "contract_id": contract_id,
        "evaluation": evaluation.model_dump(),
        "escrow": escrow.model_dump(),
        "receipt": receipt.model_dump() if receipt else None,
        "remediation": escrow.status == "REMEDIATION",
    }


@app.post("/api/contracts/draft")
async def create_draft_contract(req: ContractCreateRequest, user=Depends(require_user)) -> dict:
    errors = _validate_create(req)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    _enforce_open_contract_cap(user)
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
        state="DRAFT",
        owner_id=(user.id if user else ""),
    )
    contract.arbiter_weights = {
        "tests": config.W_TESTS, "schema": config.W_SCHEMA, "llm": config.W_LLM,
    }
    contract.deadline_hours, contract.deadline_at = deadline_from_hours(
        req.deadline_hours, config.DEADLINE_HOURS_DEFAULT, config.DEADLINE_HOURS_MAX
    )
    CONTRACTS[contract.id] = contract
    if user is not None:
        register_contract_party(user.id, contract.id)

    from . import db

    db.save_contract(contract.model_dump())
    return {
        "contract": contract.model_dump(),
        "state": "DRAFT",
        "next": f"POST /api/contracts/{contract.id}/fund/start",
        "note": "Draft contracts hold no PayPal reservation until funding completes.",
    }


@app.post("/api/contracts/{contract_id}/fund/start")
async def fund_start(contract_id: str, user=Depends(require_user)) -> dict:
    contract = party_or_404(contract_id, user)
    require_role(user, contract, "hirer", "fund contracts")
    try:
        started = await start_funding(contract)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "contract_id": contract_id,
        **started,
        "next": "POST /api/contracts/{id}/fund/complete with this order_id"
        if started["mode"] == "simulated"
        else "buyer approves this order via the PayPal JS SDK, then POST fund/complete",
    }


@app.post("/api/contracts/{contract_id}/fund/complete")
async def fund_complete(contract_id: str, body: FundCompleteRequest, user=Depends(require_user)) -> dict:
    contract = party_or_404(contract_id, user)
    require_role(user, contract, "hirer", "fund contracts")
    try:
        escrow = await complete_funding(contract, body.order_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "contract_id": contract_id,
        "escrow": escrow.model_dump(),
        "semantics": "Authorization RESERVED the funds; nothing is deposited until capture.",
    }


@app.post("/api/contracts/{contract_id}/reauthorize")
async def reauthorize_contract(contract_id: str, user=Depends(require_user)) -> dict:
    contract = party_or_404(contract_id, user)
    require_role(user, contract, "hirer", "re-authorize the escrow")
    escrow = ESCROWS.get(contract_id)
    if escrow is None:
        raise HTTPException(status_code=409, detail="contract has no escrow to re-authorize")
    try:
        escrow = await reauthorize_escrow(contract, escrow)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"contract_id": contract_id, "escrow": escrow.model_dump()}


@app.post("/api/maintenance/reconcile")
async def maintenance_reconcile(_user=Depends(require_user)) -> dict:
    findings = await reconcile_escrows()
    return {"findings": findings, "count": len(findings)}


@app.post("/api/sandbox/preview")
async def sandbox_preview(req: SandboxPreviewRequest, _user=Depends(require_user)) -> dict:
    """Wizard helper: run a hirer's draft tests against their own sample code."""
    if len(req.code or "") > config.MAX_CODE_CHARS or len(req.tests or "") > config.MAX_CODE_CHARS:
        raise HTTPException(status_code=422, detail=f"code and tests are limited to {config.MAX_CODE_CHARS} characters")
    result = await asyncio.to_thread(
        run_code_sandbox, req.code, req.tests, config.SANDBOX_TIMEOUT_SECONDS
    )
    return result


@app.get("/api/events/recent")
async def recent_events(limit: int = 40, user=Depends(require_user)) -> dict:
    capped = max(1, min(int(limit), 200))
    visible = visible_contract_ids(user)
    own = [e for e in EVENT_LOG if event_visible_to(e, visible)]
    return {"events": list(reversed(own[-capped:]))}


@app.get("/api/paypal/config")
async def paypal_config() -> dict:
    return {
        "mode": paypal.mode,
        "client_id": config.PAYPAL_CLIENT_ID if paypal.mode == "live_sandbox" else "",
        "currency": "USD",
        "intent": "AUTHORIZE",
    }


@app.get("/api/contracts/{contract_id}/submissions")
async def contract_submissions(contract_id: str, user=Depends(require_user)) -> dict:
    party_or_404(contract_id, user)
    submissions = []
    from . import db

    if db.enabled():
        data = db.load_all()
        submissions = [d for cid, d in data["deliverables"] if cid == contract_id]
    elif contract_id in DELIVERABLES:
        submissions = [DELIVERABLES[contract_id].model_dump()]
    return {"contract_id": contract_id, "submissions": submissions, "count": len(submissions)}


@app.post("/api/contracts/{contract_id}/accept")
async def accept_contract(contract_id: str, req: AcceptRequest, user=Depends(require_user)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="sign in as a worker to accept contracts")
    contract = CONTRACTS.get(contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="not found")
    escrow = ESCROWS.get(contract_id)
    if escrow is None or escrow.status != "AUTHORIZED":
        raise HTTPException(status_code=409, detail="only contracts with an active escrow can be accepted")
    if contract.state != "FUNDED":
        raise HTTPException(status_code=409, detail=f"contract state is {contract.state}, not FUNDED")

    from .db import claim_acceptance
    from .state_machine import require_transition

    worker_name = req.worker.strip() or user.username
    if not claim_acceptance(contract_id, user.id):
        raise HTTPException(status_code=409, detail="another worker already claimed this contract")
    require_transition("FUNDED", "ACCEPTED")
    contract.state = "ACCEPTED"
    contract.worker = worker_name[:64]
    contract.worker_id = user.id
    register_contract_party(user.id, contract_id)

    from . import db

    db.save_contract(contract.model_dump())
    return {
        "contract_id": contract_id,
        "contract": contract.model_dump(),
        "worker": contract.worker,
        "next": f"POST /api/contracts/{contract_id}/submit",
    }


@app.post("/api/contracts/{contract_id}/dispute")
async def dispute_contract(contract_id: str, req: DisputeRequest, user=Depends(require_user)) -> dict:
    contract = party_or_404(contract_id, user)
    escrow = ESCROWS.get(contract_id)
    if escrow is None or escrow.status not in ("AUTHORIZED", "REMEDIATION"):
        raise HTTPException(status_code=409, detail="disputes require an active escrow")
    if contract.state not in ("FUNDED", "ACCEPTED", "SUBMITTED"):
        raise HTTPException(status_code=409, detail=f"contract state is {contract.state}, cannot dispute")

    from .state_machine import require_transition

    require_transition(contract.state, "DISPUTED")
    contract.state = "DISPUTED"
    contract.dispute_reason = (req.reason or "no reason given")[:300]

    from . import db

    db.save_contract(contract.model_dump())
    from .agent_simulator import _register_event
    from .models import EventLogEntry

    _register_event(EventLogEntry(
        stage="dispute_opened", actor="protocol",
        message=f"Dispute opened on {contract_id}: {contract.dispute_reason} — arbitration frozen pending review",
        level="warn", data={"contract_id": contract_id, "reason": contract.dispute_reason},
    ))
    return {
        "contract_id": contract_id,
        "state": "DISPUTED",
        "note": "Arbitration is frozen. An operator resolves via /api/maintenance/disputes/{id}/resolve "
                "(proceed re-enables arbitration; void releases the hold).",
    }


@app.post("/api/maintenance/disputes/{contract_id}/resolve")
async def resolve_dispute(contract_id: str, req: DisputeResolveRequest, _user=Depends(require_user)) -> dict:
    import hmac as hmac_mod

    if config.ADMIN_TOKEN and not hmac_mod.compare_digest(req.admin_token, config.ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="admin token required")
    contract = CONTRACTS.get(contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"unknown contract: {contract_id}")
    escrow = ESCROWS.get(contract_id)
    if escrow is None or contract.state != "DISPUTED":
        raise HTTPException(status_code=409, detail="contract is not in DISPUTED state")

    from .state_machine import require_transition

    if req.outcome == "proceed":
        require_transition("DISPUTED", "SUBMITTED")
        contract.state = "SUBMITTED"
        from . import db

        db.save_contract(contract.model_dump())
        return {"contract_id": contract_id, "state": "SUBMITTED", "note": "dispute resolved — arbitration re-enabled"}

    require_transition("DISPUTED", "VOIDED")
    try:
        await paypal.void_authorization(escrow.authorization_id)
    except PayPalError as exc:
        if exc.kind == "already_captured":
            raise HTTPException(status_code=409, detail="authorization already captured — manual reconciliation required") from exc
        if exc.kind not in ("expired", "voided"):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    escrow.status = "VOIDED"
    escrow.settled_at = datetime.now(timezone.utc).isoformat()
    from . import db

    db.save_escrow(escrow.model_dump())
    contract.state = "VOIDED"
    db.save_contract(contract.model_dump())
    return {"contract_id": contract_id, "state": "VOIDED", "note": "dispute resolved — hold released to the hirer"}


@app.post("/api/contracts/{contract_id}/cancel")
async def cancel_contract(contract_id: str, user=Depends(require_user)) -> dict:
    contract = party_or_404(contract_id, user)
    require_role(user, contract, "hirer", "cancel contracts")
    escrow = ESCROWS.get(contract_id)
    if contract.state not in ("DRAFT", "FUNDED"):
        raise HTTPException(status_code=409, detail=f"contract state is {contract.state}, cannot cancel")

    from .state_machine import require_transition

    if escrow is not None and escrow.status == "AUTHORIZED":
        try:
            await paypal.void_authorization(escrow.authorization_id)
        except PayPalError as exc:
            if exc.kind not in ("expired", "voided"):
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        require_transition("FUNDED", "CANCELLED")
        escrow.status = "VOIDED"
        from . import db

        db.save_escrow(escrow.model_dump())
    require_transition("DRAFT", "CANCELLED") if contract.state == "DRAFT" else require_transition("FUNDED", "CANCELLED")
    contract.state = "CANCELLED"

    from . import db

    db.save_contract(contract.model_dump())
    return {"contract_id": contract_id, "state": "CANCELLED", "note": "any hold was released; no money moved"}


@app.post("/api/maintenance/sweep")
async def maintenance_sweep(_user=Depends(require_user)) -> dict:
    swept = await sweep_expired()
    return {"swept": swept, "count": len(swept)}


async def ws_events(websocket: WebSocket) -> None:
    """First frame must be {"token": "..."}; only the caller's own contract
    events are delivered afterwards."""
    logger.info(json.dumps({"level": "debug", "ws": "endpoint-entered"}))
    await websocket.accept()
    try:
        frame = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=10))
        token = str(frame.get("token", ""))
    except Exception as exc:
        logger.info(json.dumps({"level": "debug", "ws": "auth-rejected", "error": f"{type(exc).__name__}: {exc}"}))
        await websocket.close(code=1008)
        return

    from .auth import authenticate_token
    from .database import SessionLocal

    with SessionLocal() as session:
        user = authenticate_token(token, session)
    if user is None:
        await websocket.close(code=1008)
        return

    bus.clients.add((websocket, user.id))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        bus.clients.discard((websocket, user.id))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
