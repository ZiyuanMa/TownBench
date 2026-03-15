from __future__ import annotations

import re
from typing import Optional, Tuple

from engine.state import ActionCost, TerminationConfig, WorldEventRule, WorldState

TIME_PATTERN = re.compile(r"^Day (?P<day>\d+), (?P<hour>\d{2}):(?P<minute>\d{2})$")

DEFAULT_ACTION_COSTS: dict[str, ActionCost] = {
    "move_to": ActionCost(time_delta=10, energy_delta=-2),
    "inspect": ActionCost(time_delta=4, energy_delta=-1),
    "open_resource": ActionCost(time_delta=3),
    "load_skill": ActionCost(time_delta=5, energy_delta=-1),
    "check_status": ActionCost(),
    "write_note": ActionCost(time_delta=1),
    "call_action": ActionCost(time_delta=8, energy_delta=-3),
    "search": ActionCost(time_delta=2, energy_delta=-1),
}


def get_action_cost(state: WorldState, action_type: str) -> ActionCost:
    override = state.action_costs.get(action_type)
    if override is not None:
        return override.model_copy(deep=True)
    default_cost = DEFAULT_ACTION_COSTS.get(action_type)
    if default_cost is not None:
        return default_cost.model_copy(deep=True)
    return ActionCost()


def apply_action_costs(state: WorldState, action_type: str) -> ActionCost:
    cost = get_action_cost(state, action_type)
    if cost.time_delta:
        state.current_time = advance_time_label(state.current_time, cost.time_delta)
    if cost.money_delta:
        state.agent.money += cost.money_delta
    if cost.energy_delta:
        state.agent.energy = max(0, state.agent.energy + cost.energy_delta)
    if cost.inventory_delta:
        for item_id, delta in cost.inventory_delta.items():
            new_quantity = state.agent.inventory.get(item_id, 0) + delta
            if new_quantity <= 0:
                state.agent.inventory.pop(item_id, None)
            else:
                state.agent.inventory[item_id] = new_quantity
    return cost


def apply_world_rules(state: WorldState) -> list[str]:
    triggered_events: list[str] = []
    triggered_event_ids = set(state.triggered_event_ids)

    for rule in state.event_rules:
        if rule.trigger_once and rule.event_id in triggered_event_ids:
            continue
        if not _matches_world_flags(state.world_flags, rule.required_world_flags):
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

    return triggered_events


def evaluate_termination(state: WorldState, *, step_id: int) -> Tuple[bool, Optional[str]]:
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


def _matches_world_flags(current_flags: dict[str, bool], required_flags: dict[str, bool]) -> bool:
    return all(current_flags.get(flag) is expected for flag, expected in required_flags.items())
