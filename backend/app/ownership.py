"""Ownership enforcement for contract routes.

party_or_404 is the single gate every contract-scoped route must pass:
missing contract or a caller who is neither hirer nor worker gets the same
404 (no existence leak). Demo contracts are ownerless throwaways: readable by
any authenticated caller, never modifiable, excluded from lists.

With REQUIRE_AUTH=false (local dev) user is None and the API runs in
permissive mode; production defaults to true, where enforcement is active.
"""

from fastapi import HTTPException

from .agent_simulator import CONTRACTS, ESCROWS


def party_or_404(contract_id: str, user):
    contract = CONTRACTS.get(contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="not found")
    if user is None:
        return contract
    if getattr(contract, "is_demo", False):
        return contract
    if user.id not in (contract.hirer_id, contract.worker_id):
        raise HTTPException(status_code=404, detail="not found")
    return contract


def party_or_404_with_escrow(contract_id: str, user):
    contract = party_or_404(contract_id, user)
    escrow = ESCROWS.get(contract_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="not found")
    return contract, escrow


def require_role(user, contract, role: str, action: str) -> None:
    """Role rules on top of visibility. No-op in permissive dev mode."""
    if user is None or getattr(contract, "is_demo", False):
        return
    if role == "hirer" and user.id != contract.hirer_id:
        raise HTTPException(status_code=403, detail=f"only the hirer can {action}")
    if role == "worker" and user.id != contract.worker_id:
        raise HTTPException(status_code=403, detail=f"only the assigned worker can {action}")


def visible_contract_ids(user) -> set[str]:
    """Contract ids the caller may see in lists and feeds."""
    if user is None:
        return {cid for cid, c in CONTRACTS.items() if not getattr(c, "is_demo", False)}
    return {
        cid
        for cid, c in CONTRACTS.items()
        if not getattr(c, "is_demo", False)
        and user.id in (c.hirer_id, c.worker_id)
    }


def event_visible_to(event: dict, contract_ids: set[str]) -> bool:
    cid = (event.get("data") or {}).get("contract_id")
    return cid in contract_ids if cid else False
