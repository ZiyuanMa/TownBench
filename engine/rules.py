from __future__ import annotations

import re
from collections.abc import Mapping

from engine.state import ActionCost, TerminationConfig, WorldState

TIME_PATTERN = re.compile(r"^Day (?P<day>\d+), (?P<hour>\d{2}):(?P<minute>\d{2})$")


def apply_state_delta(state: WorldState, delta: ActionCost) -> ActionCost:
    applied = delta.model_copy(deep=True)
    if applied.time_delta:
        state.current_time = advance_time_label(state.current_time, applied.time_delta)
    if applied.money_delta:
        state.agent.money += applied.money_delta
    if applied.energy_delta:
        state.agent.energy = max(0, state.agent.energy + applied.energy_delta)
    if applied.inventory_delta:
        _apply_inventory_delta(state, applied.inventory_delta)
    return applied


def merge_inventory_deltas(primary: dict[str, int], secondary: dict[str, int]) -> dict[str, int]:
    merged = dict(primary)
    for item_id, delta in secondary.items():
        merged[item_id] = merged.get(item_id, 0) + delta
        if merged[item_id] == 0:
            merged.pop(item_id)
    return merged


def project_inventory(inventory: Mapping[str, int], inventory_delta: Mapping[str, int]) -> dict[str, int] | None:
    projected = dict(inventory)
    for item_id, delta in inventory_delta.items():
        new_quantity = projected.get(item_id, 0) + delta
        if new_quantity < 0:
            return None
        if new_quantity == 0:
            projected.pop(item_id, None)
            continue
        projected[item_id] = new_quantity
    return projected


def inventory_load(inventory: Mapping[str, int]) -> int:
    return sum(quantity for quantity in inventory.values() if quantity > 0)


def inventory_capacity(state: WorldState) -> int | None:
    carry_limit = state.agent.stats.get("carry_limit")
    if carry_limit is None:
        return None
    return max(0, carry_limit)


def projected_inventory_capacity(
    state: WorldState,
    agent_stat_deltas: Mapping[str, int] | None = None,
) -> int | None:
    stat_deltas = agent_stat_deltas or {}
    carry_limit = state.agent.stats.get("carry_limit")
    carry_limit_delta = stat_deltas.get("carry_limit", 0)
    if carry_limit is None and carry_limit_delta == 0:
        return None
    return max(0, (carry_limit or 0) + carry_limit_delta)


def validate_inventory_delta(
    state: WorldState,
    inventory_delta: Mapping[str, int],
    *,
    agent_stat_deltas: Mapping[str, int] | None = None,
) -> str | None:
    projected_inventory = project_inventory(state.agent.inventory, inventory_delta)
    if projected_inventory is None:
        return "insufficient_inventory"

    carry_limit = projected_inventory_capacity(state, agent_stat_deltas)
    carry_limit_changed = bool((agent_stat_deltas or {}).get("carry_limit", 0))
    if not inventory_delta and not carry_limit_changed:
        return None
    if carry_limit is not None and inventory_load(projected_inventory) > carry_limit:
        return "inventory_capacity_exceeded"
    return None


def apply_world_rules(state: WorldState) -> list[str]:
    triggered_events: list[str] = []
    triggered_event_ids = set(state.triggered_event_ids)
    active_event_ids = set(state.active_event_ids)

    for rule in state.event_rules:
        matches = matches_world_flags(state.world_flags, rule.required_world_flags)
        if rule.trigger_once and rule.event_id in triggered_event_ids:
            continue
        if not matches:
            continue
        if not rule.trigger_once and rule.event_id in active_event_ids:
            continue

        state.world_flags.update(rule.set_world_flags)
        for object_id, patch in rule.set_object_visible_state.items():
            world_object = state.objects.get(object_id)
            if world_object is None:
                continue
            world_object.visible_state.update(patch)

        triggered_events.append(rule.event_id)
        if rule.trigger_once:
            state.triggered_event_ids.append(rule.event_id)
            triggered_event_ids.add(rule.event_id)

    state.active_event_ids = [
        rule.event_id
        for rule in state.event_rules
        if matches_world_flags(state.world_flags, rule.required_world_flags)
    ]
    return triggered_events


def evaluate_termination(state: WorldState, *, step_id: int) -> tuple[bool, str | None]:
    config = state.termination_config or TerminationConfig()

    for flag in config.success_world_flags:
        if state.world_flags.get(flag):
            return True, f"success:{flag}"

    for flag in config.failure_world_flags:
        if state.world_flags.get(flag):
            return True, f"failure:{flag}"

    if config.stop_on_zero_energy and state.agent.energy <= 0:
        return True, "energy_depleted"

    if config.max_steps is not None and step_id >= config.max_steps:
        return True, "max_steps_reached"

    return False, None


def advance_time_label(value: str, minutes: int) -> str:
    total_minutes = parse_time_label(value) + minutes
    if total_minutes < 0:
        total_minutes = 0
    day, minute_of_day = divmod(total_minutes, 24 * 60)
    hour, minute = divmod(minute_of_day, 60)
    return f"Day {day + 1}, {hour:02d}:{minute:02d}"


def parse_time_label(value: str) -> int:
    match = TIME_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(f"Unsupported time format: `{value}`.")

    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if day <= 0:
        raise ValueError(f"Day must be positive in `{value}`.")
    if hour >= 24 or minute >= 60:
        raise ValueError(f"Unsupported time format: `{value}`.")
    return (day - 1) * 24 * 60 + hour * 60 + minute


def matches_world_flags(current_flags: dict[str, bool], required_flags: dict[str, bool]) -> bool:
    return all(current_flags.get(flag) is expected for flag, expected in required_flags.items())


def _apply_inventory_delta(state: WorldState, inventory_delta: dict[str, int]) -> None:
    for item_id, delta in inventory_delta.items():
        new_quantity = state.agent.inventory.get(item_id, 0) + delta
        if new_quantity <= 0:
            state.agent.inventory.pop(item_id, None)
        else:
            state.agent.inventory[item_id] = new_quantity
