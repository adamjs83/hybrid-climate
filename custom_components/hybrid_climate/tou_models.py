"""Purpose: Time-of-use (TOU) configuration dataclasses.

Key dependencies: None (plain dataclasses).
Used by: models.py (re-exports them), config_parsers.py, config_loader.py, tou_manager.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ZoneTouModeConfig:
    """TOU config for a single mode (heat or cool) within a zone."""
    pre_condition_minutes: int = 60
    relaxation_amount: float = 2.0  # °F


@dataclass
class ZoneTouConfig:
    """Per-zone TOU optimization configuration.

    Each zone can independently configure TOU behavior for heat and cool.
    If heat or cool is None, TOU does not apply for that mode.
    """
    heat: ZoneTouModeConfig | None = None
    cool: ZoneTouModeConfig | None = None


@dataclass
class TouGlobalConfig:
    """Global TOU configuration."""
    rate_sensor: str | None = None  # Entity ID of rate period sensor
