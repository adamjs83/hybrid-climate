"""Purpose: Resolve and merge the zone scope of a takeover/restore pass request.

A scope value is `None` (every zone), a single zone ID (`str`), or several zone
IDs merged together (`frozenset[str]`) — the last only ever produced by
merging two pending requests that each named a different zone (review round 1
item 1: a later request must never narrow an earlier one still waiting to
apply, or the earlier request's zones would silently lose their restore).

Key dependencies: HybridClimateConfig's zones mapping.
Used by: startup_takeover.py (StartupTakeover.request_rearm/rearm).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import HybridClimateConfig, ZoneConfig


def merge_zone_scope(
    first: str | frozenset[str] | None, second: str | frozenset[str] | None,
) -> str | frozenset[str] | None:
    """Merge two pending scopes; `None` (every zone) absorbs the other."""
    if first is None or second is None:
        return None
    first_ids = {first} if isinstance(first, str) else set(first)
    second_ids = {second} if isinstance(second, str) else set(second)
    merged = first_ids | second_ids
    return next(iter(merged)) if len(merged) == 1 else frozenset(merged)


def zones_for_scope(
    config: HybridClimateConfig, zone_id: str | frozenset[str] | None,
) -> dict[str, ZoneConfig]:
    """Resolve a scope value into the zones it covers."""
    if zone_id is None:
        return dict(config.zones)
    if isinstance(zone_id, str):
        return {zone_id: config.zones[zone_id]}
    return {zid: config.zones[zid] for zid in zone_id}
