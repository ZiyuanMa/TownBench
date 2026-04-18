from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from engine.state import ActionCost, ConditionNode, TerminationConfig, TimeWindow, WorldState

TIME_PATTERN = re.compile(r"^Day (?P<day>\d+), (?P<hour>\d{2}):(?P<minute>\d{2})$")


class RuleEvaluationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: str | None = None
    action_name: str | None = None
    action_args: dict[str, str] = Field(default_factory=dict)
    step_id: int | None = None


def apply_state_delta(state: WorldState, delta: ActionCost) -> ActionCost:
    applied = delta.model_copy(deep=True)
    if applied.time_delta:
        state.current_time = advance_time(state.current_time, applied.time_delta)
    if applied.money_delta:
        state.agent.money += applied.money_delta
    if applied.energy_delta:
        state.agent.energy = max(0, state.agent.energy + applied.energy_delta)
    if applied.inventory_delta:
        _apply_inventory_delta(state, applied.inventory_delta)
    return applied


def apply_explicit_action_cost(state: WorldState, cost: ActionCost) -> ActionCost:
    return apply_state_delta(state, cost)


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
        matches = matches_condition(state, rule.when)
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
        if matches_condition(state, rule.when)
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


def advance_time(total_minutes: int, minutes: int) -> int:
    updated_total_minutes = total_minutes + minutes
    if updated_total_minutes < 0:
        return 0
    return updated_total_minutes


def format_time_label(total_minutes: int) -> str:
    if total_minutes < 0:
        raise ValueError(f"Time must be non-negative: `{total_minutes}`.")
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


def minute_of_day(total_minutes: int) -> int:
    if total_minutes < 0:
        raise ValueError(f"Time must be non-negative: `{total_minutes}`.")
    return total_minutes % (24 * 60)


def parse_clock_time(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Unsupported clock time format: `{value}`.")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour >= 24 or minute < 0 or minute >= 60:
        raise ValueError(f"Unsupported clock time format: `{value}`.")
    return hour * 60 + minute


def matches_time_window(current_time: int, time_window: TimeWindow) -> bool:
    current_minute_of_day = minute_of_day(current_time)
    start = parse_clock_time(time_window.start)
    end = parse_clock_time(time_window.end)

    if start == end:
        return True
    if start < end:
        return start <= current_minute_of_day < end
    return current_minute_of_day >= start or current_minute_of_day < end


def matches_condition(
    state: WorldState,
    condition: ConditionNode,
    *,
    context: RuleEvaluationContext | None = None,
) -> bool:
    _ = context
    if condition.kind == "all":
        return all(matches_condition(state, child, context=context) for child in condition.children)
    if condition.kind == "any":
        return any(matches_condition(state, child, context=context) for child in condition.children)
    if condition.kind == "not":
        return not matches_condition(state, condition.children[0], context=context)
    return matches_atomic_condition(state, condition)


def matches_atomic_condition(state: WorldState, condition: ConditionNode) -> bool:
    if condition.kind == "time_window":
        if condition.time_window is None:
            return False
        return matches_time_window(state.current_time, condition.time_window)
    if condition.kind == "world_flags":
        return matches_world_flags(state.world_flags, condition.world_flags or {})
    if condition.kind == "location_id":
        return state.agent.location_id == condition.location_id
    if condition.kind == "has_inventory":
        return all(
            state.agent.inventory.get(item_id, 0) >= required_quantity
            for item_id, required_quantity in (condition.has_inventory or {}).items()
        )
    if condition.kind == "money_at_least":
        return state.agent.money >= (condition.threshold or 0)
    if condition.kind == "energy_at_least":
        return state.agent.energy >= (condition.threshold or 0)
    raise ValueError(f"Unsupported condition node kind `{condition.kind}`.")


def matches_world_flags(current_flags: dict[str, bool], required_flags: dict[str, bool]) -> bool:
    return all(current_flags.get(flag) is expected for flag, expected in required_flags.items())


def _apply_inventory_delta(state: WorldState, inventory_delta: dict[str, int]) -> None:
    for item_id, delta in inventory_delta.items():
        new_quantity = state.agent.inventory.get(item_id, 0) + delta
        if new_quantity <= 0:
            state.agent.inventory.pop(item_id, None)
        else:
            state.agent.inventory[item_id] = new_quantity
