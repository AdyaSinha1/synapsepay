from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return uuid4().hex[:12]


class TaskContract(BaseModel):
    id: str = Field(default_factory=_short_id)
    title: str
    description: str = ""
    bounty_value: float
    currency: str = "USD"
    hirer: str = "orchestrator-agent-a"
    worker: str = "worker-agent-b"
    acceptance_criteria: list[str] = Field(default_factory=list)
    deliverable_schema: dict = Field(default_factory=dict)
    test_code: str = ""
    worker_code: str = ""
    arbiter_weights: dict = Field(
        default_factory=lambda: {"tests": 0.50, "schema": 0.25, "llm": 0.25}
    )
    timeout_seconds: float = 5.0
    created_at: str = Field(default_factory=_now)


class Deliverable(BaseModel):
    artifact_type: Literal["code", "json", "svg"] = "code"
    code: str = ""
    payload: Optional[dict] = None
    notes: str = ""
    worker: str = "worker-agent-b"
    submitted_at: str = Field(default_factory=_now)


class EventLogEntry(BaseModel):
    ts: str = Field(default_factory=_now)
    stage: str
    actor: str
    message: str
    level: str = "info"
    latency_ms: Optional[int] = None
    data: dict = Field(default_factory=dict)


class SettlementReceipt(BaseModel):
    settlement_type: Literal["CAPTURE", "PARTIAL_CAPTURE", "VOID"]
    transaction_id: str
    status: str
    order_id: str
    authorization_id: str
    amount: float
    currency: str = "USD"
    captured_amount: Optional[float] = None
    released_amount: Optional[float] = None
    mode: str = "simulated"
    timestamp: str = Field(default_factory=_now)
    paypal_dashboard_url: str = "https://developer.paypal.com/dashboard/"
    notes: str = ""


class EscrowRecord(BaseModel):
    contract_id: str
    order_id: str
    authorization_id: str
    amount: float
    currency: str = "USD"
    status: Literal["AUTHORIZED", "PARTIAL", "CAPTURED", "VOIDED", "REMEDIATION"] = "AUTHORIZED"
    mode: str = "simulated"
    remediation_used: bool = False
    authorized_at: str = Field(default_factory=_now)
    settled_at: Optional[str] = None
    settlement_latency_ms: Optional[int] = None
    receipt: Optional[SettlementReceipt] = None


class EvaluationResult(BaseModel):
    contract_id: str
    scores: dict
    weights: dict
    composite: float
    threshold: float
    decision: Literal["CAPTURE", "PARTIAL", "VOID"]
    payout_fraction: float = 0.0
    remediation_plan: list[str] = Field(default_factory=list)
    test_logs: list[str] = Field(default_factory=list)
    schema_details: list[str] = Field(default_factory=list)
    llm_provider: str = "heuristic_fallback"
    llm_rationale: str = ""
    sandbox: dict = Field(default_factory=dict)
    arbiter_latency_ms: int = 0
    evaluated_at: str = Field(default_factory=_now)


class ContractCreateRequest(BaseModel):
    title: str = "Custom Agent Task"
    description: str = ""
    bounty_value: float = 25.0
    currency: str = "USD"
    acceptance_criteria: list[str] = Field(default_factory=list)
    deliverable_schema: dict = Field(default_factory=dict)
    test_code: str = ""
    worker_code: str = ""


class ExecuteDemoRequest(BaseModel):
    scenario_id: Optional[str] = None
    contract_id: Optional[str] = None


class SubmitDeliverableRequest(BaseModel):
    artifact_type: Literal["code", "json", "svg"] = "code"
    code: str = ""
    payload: Optional[dict] = None
    notes: str = ""
