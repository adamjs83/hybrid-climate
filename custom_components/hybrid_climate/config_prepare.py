"""Purpose: Prepare runtime configuration from an isolated options snapshot.

Key dependencies: UI converter, validated config loader, and options applier.
Used by: Integration setup and future Agent API validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .config_applier import apply_options_to_config
from .config_converter import build_config_from_ui
from .config_loader import load_config
from .const import CONF_UI_CONFIG
from .models import HybridClimateConfig


def prepare_runtime_config(options: Mapping[str, Any]) -> HybridClimateConfig:
    """Run setup's pure configuration preparation against an isolated snapshot."""
    snapshot = deepcopy(dict(options))
    config = load_config(build_config_from_ui(snapshot.get(CONF_UI_CONFIG, {})))
    apply_options_to_config(config, snapshot)
    return config
