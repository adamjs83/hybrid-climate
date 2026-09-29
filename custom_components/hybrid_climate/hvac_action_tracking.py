"""Purpose: Stamp when a zone's cached hvac_action last actually changed.

Key dependencies: models.ZoneState.
Used by: coordinator.py, once per cycle after reconcile_dispatch (the last
point in the cycle that can still mutate hvac_action — opportunistic heating
activations and dispatch-reconciliation rollbacks both happen earlier). Read
only by the Agent API status projection (agent_api/status.py); control never
reads ZoneState.hvac_action_since.
"""

from __future__ import annotations

from homeassistant.util import dt as dt_util

from .models import ZoneState


def stamp_hvac_action_transitions(
    zone_states: dict[str, ZoneState], previous_states: dict[str, ZoneState],
) -> None:
    """Record hvac_action_since for zones whose cached hvac_action changed this cycle.

    Compares each zone's final post-dispatch state against the pre-cycle
    snapshot taken before the zone loop ran, so a command failure that
    reconcile_dispatch rolls back is never stamped as a transition. A zone
    whose previous snapshot was never evaluated (last_update is None, i.e. a
    freshly restarted integration) is skipped, so hvac_action_since stays None
    until the first real transition instead of stamping a false transition
    away from the default state.
    """
    now = dt_util.utcnow()
    for zone_id, state in zone_states.items():
        previous = previous_states.get(zone_id)
        if previous is None or previous.last_update is None:
            continue
        if state.hvac_action != previous.hvac_action:
            state.hvac_action_since = now
