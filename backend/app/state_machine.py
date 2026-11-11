"""Centralized escrow state machine.

One vocabulary, one allowed-transition table, one enforcement point. The
legacy demo statuses map onto the canonical names:

    AUTHORIZED -> FUNDED      (PayPal hold reserved, not deposited)
    CAPTURED   -> SETTLED     (capture completed the charge)

Terminal states accept no further transitions. Every escrow mutation should
go through require_transition; illegal moves raise ValueError.
"""

ALIASES = {
    "AUTHORIZED": "FUNDED",
    "CAPTURED": "SETTLED",
}

ALLOWED = {
    "DRAFT": {"FUNDED", "CANCELLED"},
    "FUNDED": {
        "ACCEPTED", "SUBMITTED", "ARBITRATING",
        "SETTLED", "VOIDED", "CANCELLED", "EXPIRED",
    },
    "ACCEPTED": {"SUBMITTED", "CANCELLED", "EXPIRED"},
    "SUBMITTED": {"ARBITRATING", "CANCELLED", "EXPIRED"},
    "ARBITRATING": {"SETTLED", "PARTIAL", "VOIDED", "REMEDIATION", "FUNDED"},
    "REMEDIATION": {"ARBITRATING", "SETTLED", "PARTIAL", "VOIDED", "EXPIRED"},
    "SETTLED": set(),
    "PARTIAL": set(),
    "VOIDED": set(),
    "EXPIRED": set(),
    "CANCELLED": set(),
}

TERMINAL = {state for state, targets in ALLOWED.items() if not targets}


def canonical(status: str) -> str:
    return ALIASES.get(status, status)


def can_transition(current: str, new: str) -> bool:
    return canonical(new) in ALLOWED.get(canonical(current), set())


def require_transition(current: str, new: str) -> str:
    current_c, new_c = canonical(current), canonical(new)
    if new_c not in ALLOWED.get(current_c, set()):
        raise ValueError(f"illegal escrow transition: {current} -> {new}")
    return new_c


def is_terminal(status: str) -> bool:
    return canonical(status) in TERMINAL
