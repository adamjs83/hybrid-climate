"""Purpose: Validate scalar tuning values without coercion.

Key dependencies: Field metadata and finite-number checks.
Used by: Stored accessors and outdoor override writer.
"""

from __future__ import annotations

import math
from typing import Any

from .fields import Field


def validate_value(field: Field, value: Any) -> Any:
    """Strictly validate a writable value without coercing strings or booleans."""
    if field.key == "time_escalation" and value is None:
        return None
    if field.kind == "bool":
        if type(value) is not bool:
            raise ValueError("Expected boolean")
        return value
    if field.kind == "enum":
        if not isinstance(value, str) or value not in field.enum:
            raise ValueError(f"Expected one of {field.enum}")
        return value
    if type(value) not in (int, float):
        raise ValueError("Expected finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError as error:
        raise ValueError("Expected finite number") from error
    if not finite:
        raise ValueError("Expected finite number")
    if field.kind == "int" and int(value) != value:
        raise ValueError("Expected integer")
    if field.minimum is not None and value < field.minimum:
        raise ValueError(f"Minimum is {field.minimum}")
    if field.maximum is not None and value > field.maximum:
        raise ValueError(f"Maximum is {field.maximum}")
    return int(value) if field.kind == "int" else float(value)
