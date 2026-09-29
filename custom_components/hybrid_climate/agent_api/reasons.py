"""Purpose: Explain recorded zone restrictions without inferring control decisions.

Key dependencies: Diagnostics reason codes and cached zone state.
Used by: Agent API status projection.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ZoneState
from .const import REASON_DETAILS, UNKNOWN_REASON_DETAIL


def zone_reasons(snapshot: Mapping[str, Any], state: ZoneState) -> list[dict[str, Any]]:
    """Explain only recorded restrictions; unknown is preferable to a guessed cause."""
    result = [
        {"code": code, "detail": REASON_DETAILS[code]}
        for code in snapshot["blocking_reasons"] if code in REASON_DETAILS
    ]
    for reason in result:
        if reason["code"] == "opening_lockout" and state.opening_changed_at:
            reason["since"] = state.opening_changed_at.isoformat()
    return result or [{"code": "unknown", "detail": UNKNOWN_REASON_DETAIL}]
