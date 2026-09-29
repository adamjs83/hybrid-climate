"""Purpose: Exclude devices unable to heat from loaded PI regulation.

Key dependencies: Loaded device and zone models.
Used by: The shared YAML and UI configuration loader.
"""

from __future__ import annotations

import logging

from .const import REGULATION_IGNORED_DEVICE_WARNING, REGULATION_PI
from .models import HybridClimateConfig

_LOGGER = logging.getLogger(__name__)


def filter_regulation_devices(config: HybridClimateConfig) -> None:
    """Keep only heat-capable PI devices in each loaded zone."""
    for zone_id, zone in config.zones.items():
        regulation = zone.regulation
        if regulation is None or regulation.type != REGULATION_PI:
            continue
        effective: list[str] = []
        ignored: list[str] = []
        for device_id in regulation.devices:
            device = config.devices.get(device_id)
            if device is not None and device.can_heat():
                effective.append(device_id)
            else:
                ignored.append(device_id)
        regulation.devices = effective
        regulation.ignored_devices = ignored
        for device_id in dict.fromkeys(ignored):
            _LOGGER.warning(REGULATION_IGNORED_DEVICE_WARNING, zone_id, device_id)
