"""Parse the plan's dollar credit grant out of the usage payload."""

from __future__ import annotations

from typing import Any


def parse_credit(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the credit grant's remaining dollars, limit and reset time.

    The grant sits under a codename top-level key ("iguana_necktie" as of
    2026-10) that may change, so it is found by its fields rather than its key.
    The five_hour and seven_day windows carry the same fields set to null, so
    only a bucket with a limit counts as the grant.
    """
    for value in raw.values():
        if isinstance(value, dict) and value.get("limit_dollars") is not None:
            remaining = value.get("remaining_dollars")
            return {
                "credit_remaining": round(remaining, 2) if remaining is not None else None,
                "credit_limit": value.get("limit_dollars"),
                "credit_reset_time": value.get("resets_at"),
            }
    return {}
