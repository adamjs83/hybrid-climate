"""Purpose: One delete-confirmation step for zones, heat source groups and mutex rules, listing what refers to the item (v0.17.0 §0.10).

Key dependencies: options_flow/page_const.py, const.py; the delete helpers (_delete_zone, _delete_heat_source,
_delete_conflict) and list steps of the composed flow.
Used by: options_flow/zones.py, heat_sources.py, conflicts.py (delete_<id> calls the _confirm_* methods);
handler.py composes DeleteConfirmMixin.
"""
from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ...const import (
    CONF_BLOCK_COOL,
    CONF_BLOCK_HEAT,
    CONF_CONFLICTS,
    CONF_DEVICE_MUTEX,
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_HEAT_SOURCES,
    CONF_HEAT_STAGES,
    CONF_NAME,
    CONF_ZONES,
)
from ..base import OptionsFlowBase
from ..zone_merge import canonical_device, canonical_stages
from ..page_const import (
    CONF_BLOCKED_DEVICES_COOL,
    CONF_BLOCKED_DEVICES_HEAT,
    DELETE_ITEM_HEAT_SOURCE,
    DELETE_ITEM_RULE,
    DELETE_ITEM_ZONE,
    DELETE_KIND_HEAT_SOURCE,
    DELETE_KIND_RULE,
    DELETE_KIND_ZONE,
    DELETE_NAV_CANCEL,
    DELETE_NAV_DELETE,
    DELETE_NAV_OPTIONS,
    DELETE_NO_REFERENCES,
    DELETE_REFERENCE_LINE,
    DELETE_REFERENCES_HEADER,
    REF_RULE,
    REF_RULE_BLOCKS_COOL,
    REF_RULE_BLOCKS_HEAT,
    REF_RULE_DEVICE,
    REF_UNKNOWN,
    REF_ZONE_STAGE1_HEAT,
    STEP_DELETE_CONFIRM,
)

# Abort reasons, unchanged from the pre-v0.17.0 delete actions (strings.json options.abort).
ABORT_YAML_ZONE = "cannot_delete_yaml_zone"
ABORT_YAML_SOURCE = "cannot_delete_yaml_source"
ABORT_YAML_RULE = "cannot_delete_yaml_rule"
ABORT_RULE_NOT_FOUND = "rule_not_found"
ABORT_RULE_CHANGED = "rule_changed"
RULE_WHEN = "when"
RULE_THEN = "then"
RULE_DEVICE = "device"
RULE_DEVICE_ID = "device_id"
RULE_MODE = "mode"
RULE_FOR_ZONE = "for_zone"
STAGE_NUMBER = "stage"


def _flat_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Return a mutex rule in the flat UI form (YAML rules nest their keys under when/then)."""
    if RULE_WHEN in rule or RULE_THEN in rule:
        return {**(rule.get(RULE_WHEN) or {}), **(rule.get(RULE_THEN) or {})}
    return rule


def _rule_line(rule: dict[str, Any]) -> str:
    """Describe a rule as "Rule: <device> (<mode> in <zone>)"."""
    return REF_RULE.format(
        device=rule.get(RULE_DEVICE) or rule.get(RULE_DEVICE_ID) or REF_UNKNOWN,
        mode=rule.get(RULE_MODE) or REF_UNKNOWN,
        zone=rule.get(RULE_FOR_ZONE) or REF_UNKNOWN,
    )


def _entity_ids(devices: list[Any]) -> list[str]:
    """Return the entity ids of a stage device list (dicts with entity_id, or plain strings)."""
    result: list[str] = []
    for device in devices or []:
        entity_id = device.get(CONF_ENTITY_ID) if isinstance(device, dict) else device
        if isinstance(entity_id, str) and entity_id:
            result.append(entity_id)
    return result


def zone_references(
    ui_config: dict[str, Any], zone_id: str, yaml_rules: list[dict[str, Any]] | None = None,
) -> list[str]:
    """List the mutex rules (YAML first, then UI) that name the zone as trigger or blocked zone."""
    # Mutex rules are the only ui_config blocks that refer to a zone by id.
    rules = list(yaml_rules or []) + list(ui_config.get(CONF_DEVICE_MUTEX) or [])
    refs: list[str] = []
    for raw in rules:
        if not isinstance(raw, dict):
            continue
        rule = _flat_rule(raw)
        blocked = list(rule.get(CONF_BLOCK_HEAT) or []) + list(rule.get(CONF_BLOCK_COOL) or [])
        if rule.get(RULE_FOR_ZONE) == zone_id or zone_id in blocked:
            refs.append(_rule_line(rule))
    return refs


def heat_source_references(
    ui_config: dict[str, Any], source_id: str, yaml_config: dict[str, Any] | None = None,
) -> list[str]:
    """List the zones (UI, then YAML-only) whose stage-1 heat devices belong to the heat source group."""
    yaml_config = yaml_config or {}
    yaml_devices = yaml_config.get(CONF_DEVICES) or {}
    source = (ui_config.get(CONF_HEAT_SOURCES) or {}).get(source_id)
    if not isinstance(source, dict):
        return []
    # Members and stage devices may be YAML device ids; compare them as entity ids (zone_merge rule).
    members = {canonical_device(ref, yaml_devices).get(CONF_ENTITY_ID) for ref in source.get(CONF_DEVICES) or []}
    # UI zones override YAML zones of the same id, as in the zone list.
    zones = {**(yaml_config.get(CONF_ZONES) or {}), **(ui_config.get(CONF_ZONES) or {})}
    refs: list[str] = []
    for zone_id, zone in sorted(zones.items()):
        stages = canonical_stages(zone.get(CONF_HEAT_STAGES), yaml_devices)
        # Stage 1 is the stage numbered 1, or the first listed when stages carry no number.
        first = next((stage for stage in stages if stage.get(STAGE_NUMBER) == 1), stages[0] if stages else None)
        shared = [eid for eid in _entity_ids((first or {}).get(CONF_DEVICES, [])) if eid in members]
        if shared:
            refs.append(REF_ZONE_STAGE1_HEAT.format(name=zone.get(CONF_NAME, zone_id), devices=", ".join(shared)))
    return refs


def rule_references(rule: dict[str, Any]) -> list[str]:
    """List the rule's device and the devices it blocks from heating or cooling."""
    rule = _flat_rule(rule)
    refs = [REF_RULE_DEVICE.format(device=rule.get(RULE_DEVICE) or rule.get(RULE_DEVICE_ID) or REF_UNKNOWN)]
    for key, template in ((CONF_BLOCKED_DEVICES_HEAT, REF_RULE_BLOCKS_HEAT),
                          (CONF_BLOCKED_DEVICES_COOL, REF_RULE_BLOCKS_COOL)):
        if rule.get(key):
            refs.append(template.format(devices=", ".join(rule[key])))
    return refs


def references_text(refs: list[str]) -> str:
    """Render the reference list for the confirm description."""
    if not refs:
        return DELETE_NO_REFERENCES
    return "\n".join([DELETE_REFERENCES_HEADER, *(DELETE_REFERENCE_LINE.format(reference=ref) for ref in refs)])


class DeleteConfirmMixin(OptionsFlowBase):
    """Mixin providing the delete confirmation step and its three entry points."""

    _delete_kind: str | None = None
    _delete_target: str | int | None = None
    _delete_placeholders: dict[str, str] | None = None
    # A rule is deleted by list index, so remember what the confirm showed: (YAML rule count, stored rule).
    _delete_rule: tuple[int, dict[str, Any]] | None = None

    def _yaml_rules(self) -> list[dict[str, Any]]:
        """Return the YAML mutex rules (they come first in the conflicts list index)."""
        return list(self._get_yaml_config().get(CONF_CONFLICTS, {}).get(CONF_DEVICE_MUTEX, []))

    async def _confirm_zone_delete(self, zone_id: str) -> FlowResult:
        """Confirm deleting a UI zone; a YAML-only zone aborts as before."""
        ui_config = self._get_ui_config()
        zones = ui_config.get(CONF_ZONES, {})
        if not isinstance(zones, dict) or zone_id not in zones:
            return self.async_abort(reason=ABORT_YAML_ZONE)
        item = DELETE_ITEM_ZONE.format(name=zones[zone_id].get(CONF_NAME, zone_id))
        refs = zone_references(ui_config, zone_id, self._yaml_rules())
        return self._show_delete_confirm(DELETE_KIND_ZONE, zone_id, item, refs)

    async def _confirm_source_delete(self, source_id: str) -> FlowResult:
        """Confirm deleting a UI heat source group; a YAML-only group aborts as before."""
        ui_config = self._get_ui_config()
        sources = ui_config.get(CONF_HEAT_SOURCES, {})
        if not isinstance(sources, dict) or source_id not in sources:
            return self.async_abort(reason=ABORT_YAML_SOURCE)
        item = DELETE_ITEM_HEAT_SOURCE.format(name=sources[source_id].get(CONF_NAME, source_id))
        refs = heat_source_references(ui_config, source_id, self._get_yaml_config())
        return self._show_delete_confirm(DELETE_KIND_HEAT_SOURCE, source_id, item, refs)

    async def _confirm_rule_delete(self, idx: int) -> FlowResult:
        """Confirm deleting a UI mutex rule by list index; YAML rules and bad indexes abort as before."""
        yaml_count = len(self._yaml_rules())
        if idx < yaml_count:
            return self.async_abort(reason=ABORT_YAML_RULE)
        rules = self._get_ui_config().get(CONF_DEVICE_MUTEX, [])
        ui_idx = idx - yaml_count
        if not isinstance(rules, list) or not 0 <= ui_idx < len(rules):
            return self.async_abort(reason=ABORT_RULE_NOT_FOUND)
        self._delete_rule = (yaml_count, copy.deepcopy(rules[ui_idx]))
        rule = _flat_rule(rules[ui_idx])
        item = DELETE_ITEM_RULE.format(
            device=rule.get(RULE_DEVICE) or REF_UNKNOWN,
            mode=rule.get(RULE_MODE) or REF_UNKNOWN,
            zone=rule.get(RULE_FOR_ZONE) or REF_UNKNOWN,
        )
        return self._show_delete_confirm(DELETE_KIND_RULE, idx, item, rule_references(rule))

    def _show_delete_confirm(self, kind: str, target: str | int, item: str, refs: list[str]) -> FlowResult:
        """Remember what is being deleted and show the confirm form."""
        self._delete_kind = kind
        self._delete_target = target
        self._delete_placeholders = {"item": item, "references": references_text(refs)}
        return self._delete_confirm_form()

    def _delete_confirm_form(self) -> FlowResult:
        """Render the confirm form: navigation only, Cancel preselected."""
        return self.async_show_form(
            step_id=STEP_DELETE_CONFIRM,
            data_schema=vol.Schema({
                vol.Required("nav_action", default=DELETE_NAV_CANCEL): SelectSelector(
                    SelectSelectorConfig(options=DELETE_NAV_OPTIONS, mode=SelectSelectorMode.LIST)
                ),
            }),
            description_placeholders=dict(self._delete_placeholders or {}),
        )

    async def async_step_delete_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Delete the remembered item on "delete"; otherwise return to its list unchanged."""
        kind, target = self._delete_kind, self._delete_target
        if kind is None or target is None:
            return await self.async_step_menu()
        if user_input is None:
            return self._delete_confirm_form()
        self._delete_kind = self._delete_target = self._delete_placeholders = None
        # Zones and groups are deleted by id and the helpers re-check storage; rules go by index,
        # so _delete_confirmed_rule first checks the index still holds the confirmed rule.
        if user_input.get("nav_action") == DELETE_NAV_DELETE:
            if kind == DELETE_KIND_ZONE:
                return self._delete_zone(str(target))
            if kind == DELETE_KIND_HEAT_SOURCE:
                return self._delete_heat_source(str(target))
            return self._delete_confirmed_rule(int(target))
        if kind == DELETE_KIND_ZONE:
            return await self.async_step_zones()
        if kind == DELETE_KIND_HEAT_SOURCE:
            return await self.async_step_heat_sources()
        return await self.async_step_conflicts()

    def _delete_confirmed_rule(self, idx: int) -> FlowResult:
        """Delete the rule at idx only if fresh storage still holds the rule the confirm showed there."""
        remembered, self._delete_rule = self._delete_rule, None
        rules = self._get_ui_config().get(CONF_DEVICE_MUTEX, [])
        yaml_count = len(self._yaml_rules())
        ui_idx = idx - yaml_count
        # Another session may have removed or reordered rules: never delete a different one.
        if (remembered is None or remembered[0] != yaml_count or not isinstance(rules, list)
                or not 0 <= ui_idx < len(rules) or rules[ui_idx] != remembered[1]):
            return self.async_abort(reason=ABORT_RULE_CHANGED)
        return self._delete_conflict(idx)
