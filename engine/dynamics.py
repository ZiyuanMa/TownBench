from __future__ import annotations

from dataclasses import dataclass

from engine.rules import minute_of_day
from engine.state import DynamicRule, ObjectActionEffect, TimeWindow, WorldObject, WorldState


@dataclass(frozen=True)
class EffectiveObjectView:
    object: WorldObject
    disabled_actions: tuple[str, ...]
    active_rule_ids: tuple[str, ...]


def resolve_active_dynamic_rules(
    state: WorldState,
    *,
    at_time: int | None = None,
) -> list[DynamicRule]:
    active_rules = [
        rule
        for rule in state.dynamic_rules
        if matches_time_window((state.current_time if at_time is None else at_time), rule.when.time_window)
    ]
    return sorted(active_rules, key=lambda rule: rule.priority)


def build_effective_object_view(
    state: WorldState,
    object_id: str,
    *,
    at_time: int | None = None,
) -> EffectiveObjectView | None:
    world_object = state.objects.get(object_id)
    if world_object is None:
        return None

    effective_object = world_object.model_copy(deep=True)
    action_availability = {action_name: True for action_name in effective_object.action_ids}
    active_rule_ids: list[str] = []

    for rule in resolve_active_dynamic_rules(state, at_time=at_time):
        override = rule.apply.object_overrides.get(object_id)
        if override is None:
            continue

        active_rule_ids.append(rule.rule_id)
        if override.visible_state:
            effective_object.visible_state.update(override.visible_state)
        if override.disabled_actions:
            for action_name in override.disabled_actions:
                action_availability[action_name] = False
        if override.enabled_actions:
            for action_name in override.enabled_actions:
                action_availability[action_name] = True
        for action_name, effect_override in override.action_overrides.items():
            base_effect = effective_object.action_effects.get(action_name)
            if base_effect is None:
                continue
            effective_object.action_effects[action_name] = apply_action_effect_override(base_effect, effect_override)

    disabled_actions = tuple(
        sorted(action_name for action_name, is_enabled in action_availability.items() if not is_enabled)
    )
    if disabled_actions:
        effective_object.action_ids = [
            action_name for action_name in effective_object.action_ids if action_availability.get(action_name, True)
        ]

    return EffectiveObjectView(
        object=effective_object,
        disabled_actions=disabled_actions,
        active_rule_ids=tuple(active_rule_ids),
    )


def build_effective_action_effect(
    state: WorldState,
    object_id: str,
    action_name: str,
    *,
    at_time: int | None = None,
) -> ObjectActionEffect | None:
    effective_view = build_effective_object_view(state, object_id, at_time=at_time)
    if effective_view is None:
        return None
    return effective_view.object.action_effects.get(action_name)


def apply_action_effect_override(
    base_effect: ObjectActionEffect,
    effect_override,
) -> ObjectActionEffect:
    updated_effect = base_effect.model_copy(deep=True)
    override_data = effect_override.model_dump(exclude_none=True)
    for field_name, value in override_data.items():
        setattr(updated_effect, field_name, value)
    return updated_effect


def matches_time_window(current_time: int, time_window: TimeWindow) -> bool:
    current_minute_of_day = minute_of_day(current_time)
    start = parse_clock_time(time_window.start)
    end = parse_clock_time(time_window.end)

    if start == end:
        return True
    if start < end:
        return start <= current_minute_of_day < end
    return current_minute_of_day >= start or current_minute_of_day < end


def parse_clock_time(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Unsupported clock time format: `{value}`.")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour >= 24 or minute < 0 or minute >= 60:
        raise ValueError(f"Unsupported clock time format: `{value}`.")
    return hour * 60 + minute
