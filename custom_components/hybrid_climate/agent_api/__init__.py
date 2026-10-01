"""Purpose: Register permanent Agent API services during integration setup.

Key dependencies: Home Assistant service registry and Agent API schemas.
Used by: Hybrid Climate integration setup.
"""

from __future__ import annotations

from functools import partial

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.loader import async_get_integration

from ..const import DOMAIN
from .const import (
    SERVICE_GET_CONFIG, SERVICE_GET_STATUS, SERVICE_RESTORE_CONTROL, SERVICE_SET_CONFIG,
)
from .revision import ledger


async def async_register_services(hass: HomeAssistant) -> None:
    """Register permanent administrator-only services once per HA process."""
    # Keep revision helpers importable in test environments without voluptuous.
    from .service_handlers import async_handle_restore_control, async_handle_service
    from .service_schemas import CONFIG_SCHEMA, RESTORE_SCHEMA, SET_SCHEMA, STATUS_SCHEMA

    state = ledger(hass)
    if state.get("registered"):
        return
    integration = await async_get_integration(hass, DOMAIN)
    state["version"] = integration.version
    handler = partial(async_handle_service, hass)
    restore_handler = partial(async_handle_restore_control, hass)
    for name, schema, response, service_handler in (
        (SERVICE_GET_STATUS, STATUS_SCHEMA, SupportsResponse.ONLY, handler),
        (SERVICE_GET_CONFIG, CONFIG_SCHEMA, SupportsResponse.ONLY, handler),
        (SERVICE_SET_CONFIG, SET_SCHEMA, SupportsResponse.OPTIONAL, handler),
        (SERVICE_RESTORE_CONTROL, RESTORE_SCHEMA, SupportsResponse.OPTIONAL, restore_handler),
    ):
        hass.services.async_register(DOMAIN, name, service_handler,
                                     schema=schema, supports_response=response)
    state["registered"] = True
