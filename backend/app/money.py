"""Money helpers: integer minor units (cents) with explicit rounding.

All money computation funnels through here. Rules:
- Values arrive as float dollars (wire/UI) and are converted to integer cents
  with Decimal(str(x)) + ROUND_HALF_UP at the boundary — never float arithmetic.
- Splits are exact: captured + released == total, remainder keeps every cent.
- PayPal payloads take 2-decimal strings formatted from cents.
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_cents(value: float | int | str) -> int:
    """Convert a dollar amount to integer cents with explicit rounding."""
    d = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    return int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> float:
    """Convert integer cents back to a 2-decimal float for the API/UI."""
    return float((Decimal(cents) / 100).quantize(CENT))


def paypal_amount(cents: int) -> str:
    """Format cents as PayPal's required 2-decimal string."""
    return f"{from_cents(cents):.2f}"


def partial_split(total_cents: int, fraction: float) -> tuple[int, int]:
    """Split an escrow into (captured, released) cents for a partial payout.

    The captured share is rounded HALF_UP and clamped to [0, total]; the
    released share is the exact remainder, so the two always sum to total.
    """
    clamped = min(1.0, max(0.0, float(fraction)))
    captured = int(
        (Decimal(total_cents) * Decimal(str(clamped))).to_integral_value(rounding=ROUND_HALF_UP)
    )
    captured = min(total_cents, max(0, captured))
    return captured, total_cents - captured
