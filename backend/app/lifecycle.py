"""Escrow lifecycle operations beyond a single arbitration cycle:
reconciliation against PayPal state, re-authorization of aging holds, and
the DRAFT -> FUNDED funding flow (simulated one-click or PayPal JS SDK
approval on the live path).
"""

from datetime import datetime, timedelta, timezone

from . import config
from . import db
from . import money
from .agent_simulator import (
    CONTRACTS,
    ESCROWS,
    EventLogEntry,
    _register_event,
    _now,
    paypal,
    PayPalError,
    require_transition,
)
from .models import EscrowRecord, TaskContract

REAUTHORIZE_AFTER_DAYS = 26


from .terms import lock_contract_terms, terms_hash_of  # noqa: F401

REAUTHORIZE_AFTER_DAYS = 26


def reauthorization_recommended(escrow) -> bool:
    """PayPal authorizations expire after ~29 days; honored holds are often
    shorter. Recommend a fresh hold shortly before that window closes."""
    if escrow is None or escrow.status != "AUTHORIZED":
        return False
    try:
        authorized = datetime.fromisoformat(escrow.authorized_at)
    except (TypeError, ValueError):
        return False
    if authorized.tzinfo is None:
        authorized = authorized.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - authorized > timedelta(days=REAUTHORIZE_AFTER_DAYS)

async def reconcile_escrows() -> list[dict]:
    """Compare local escrow state with PayPal's authorization state and flag
    or repair drift. In simulated mode the simulator's internal state is the
    source of truth; live mode queries the PayPal API."""
    findings: list[dict] = []
    for cid, escrow in list(ESCROWS.items()):
        if escrow.status not in ("AUTHORIZED", "ARBITRATING", "REMEDIATION"):
            continue
        if paypal.mode == "live_sandbox":
            try:
                remote = (await paypal.get_authorization_status(escrow.authorization_id)).get("status")
            except PayPalError as exc:
                findings.append({"contract_id": cid, "kind": "lookup_error", "detail": str(exc)[:200]})
                continue
        else:
            remote = paypal.sim_authorization_state(escrow.authorization_id)
            if remote is None:
                continue

        if remote in ("VOIDED", "EXPIRED"):
            escrow.status = "VOIDED"
            escrow.last_error = f"reconciled from PayPal: authorization is {remote} locally {escrow.status} was assumed"
            db.save_escrow(escrow.model_dump())
            findings.append({"contract_id": cid, "kind": "released", "remote": remote})
            _register_event(EventLogEntry(
                stage="reconciliation", actor="paypal-vault",
                message=f"Reconciliation: authorization for {cid} is {remote} at PayPal — local escrow marked VOIDED",
                level="warn", data={"contract_id": cid, "remote": remote},
            ))
        elif remote == "CAPTURED":
            escrow.status = "CAPTURED"
            escrow.last_error = "reconciled from PayPal: authorization already captured — flagged for review"
            db.save_escrow(escrow.model_dump())
            findings.append({"contract_id": cid, "kind": "captured", "remote": remote})
            _register_event(EventLogEntry(
                stage="flagged_for_review", actor="paypal-vault",
                message=f"Reconciliation: authorization for {cid} already captured at PayPal — conflict flagged for review",
                level="error", data={"contract_id": cid, "remote": remote},
            ))
        elif remote not in ("APPROVED", "CREATED", "PENDING", "PARTIALLY_CAPTURED"):
            escrow.last_error = f"reconciliation mismatch: PayPal reports {remote}"
            db.save_escrow(escrow.model_dump())
            findings.append({"contract_id": cid, "kind": "mismatch", "remote": remote, "local": escrow.status})
            _register_event(EventLogEntry(
                stage="reconciliation", actor="paypal-vault",
                message=f"Reconciliation mismatch for {cid}: PayPal reports {remote}, local escrow is {escrow.status}",
                level="error", data={"contract_id": cid, "remote": remote},
            ))
    return findings


async def reauthorize_escrow(contract: TaskContract, escrow: EscrowRecord) -> EscrowRecord:
    """Release the aging hold and place a fresh one for the same contract."""
    if escrow.status != "AUTHORIZED":
        raise ValueError(f"reauthorization requires an AUTHORIZED escrow (found {escrow.status})")
    old_authorization = escrow.authorization_id
    try:
        await paypal.void_authorization(old_authorization)
    except PayPalError:
        pass  # expired/voided holds need no release
    order = await paypal.create_authorized_order(
        escrow.amount, escrow.currency, f"SynapsePay escrow (re-authorized): {contract.title}"
    )
    auth = await paypal.authorize_order(order["order_id"])
    escrow.order_id = order["order_id"]
    escrow.authorization_id = auth["authorization_id"]
    escrow.status = "AUTHORIZED"
    escrow.authorized_at = _now()
    escrow.last_error = None
    ESCROWS[contract.id] = escrow
    db.save_escrow(escrow.model_dump())
    _register_event(EventLogEntry(
        stage="paypal_authorized", actor="paypal-vault",
        message=f"Re-authorization complete for {contract.id}: {old_authorization} -> "
                f"{escrow.authorization_id} (old hold released, fresh hold reserved)",
        level="info", data={"contract_id": contract.id,
                            "authorization_id": escrow.authorization_id,
                            "previous_authorization_id": old_authorization},
    ))
    return escrow


async def start_funding(contract: TaskContract) -> dict:
    """Create the PayPal order for a DRAFT contract (no hold yet)."""
    existing = ESCROWS.get(contract.id)
    if existing is not None and existing.status != "DRAFT":
        raise ValueError(f"contract {contract.id} already has an escrow in status {existing.status}")
    order = await paypal.create_authorized_order(
        contract.bounty_value, contract.currency, f"SynapsePay escrow: {contract.title}"
    )
    escrow = EscrowRecord(
        contract_id=contract.id,
        order_id=order["order_id"],
        authorization_id="",
        amount=contract.bounty_value,
        currency=contract.currency,
        amount_cents=money.to_cents(contract.bounty_value),
        status="DRAFT",
        mode=order["mode"],
    )
    ESCROWS[contract.id] = escrow
    db.save_escrow(escrow.model_dump())
    return {"order_id": order["order_id"], "mode": order["mode"], "status": "DRAFT"}


async def complete_funding(contract: TaskContract, order_id: str) -> EscrowRecord:
    """Authorize the (buyer-approved) order: DRAFT -> FUNDED."""
    escrow = ESCROWS.get(contract.id)
    if escrow is None or escrow.status != "DRAFT":
        raise ValueError(f"contract {contract.id} has no DRAFT escrow to fund")
    if escrow.order_id != order_id:
        raise ValueError("order_id does not match the pending funding order")
    auth = await paypal.authorize_order(order_id)
    require_transition("DRAFT", "FUNDED")
    lock_contract_terms(contract)
    escrow.authorization_id = auth["authorization_id"]
    escrow.status = "AUTHORIZED"
    escrow.authorized_at = _now()
    contract.state = "FUNDED"
    ESCROWS[contract.id] = escrow
    db.save_escrow(escrow.model_dump())
    db.save_contract(contract.model_dump())
    _register_event(EventLogEntry(
        stage="paypal_authorized", actor="paypal-vault",
        message=f"Funding complete for {contract.id}: authorization {escrow.authorization_id} "
                f"reserves ${escrow.amount:.2f} {escrow.currency} (simulated: {escrow.mode})",
        level="info", data={"contract_id": contract.id,
                            "authorization_id": escrow.authorization_id},
    ))
    return escrow
