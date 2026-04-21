from __future__ import annotations

from dataclasses import dataclass

from engine.callable_actions import (
    CallableActionAvailabilityOperation,
    CallableActionResolutionError,
    filter_callable_action_definitions,
    resolve_callable_action,
)
from engine.rules import matches_condition, matches_time_window
from engine.state import (
    CallableActionMatcher,
    DynamicRule,
    ObjectActionEffect,
    WorldObject,
    WorldState,
)


@dataclass(frozen=True)
class EffectiveObjectView:
    object: WorldObject
    disabled_routes: tuple[CallableActionMatcher, ...]
    active_rule_ids: tuple[str, ...]


def resolve_active_dynamic_rules(
    state: WorldState,
    *,
    at_time: int | None = None,
) -> list[DynamicRule]:
    evaluation_state = state
    if at_time is not None and at_time != state.current_time:
        evaluation_state = state.model_copy(update={"current_time": at_time})

    active_rules = [
        rule
        for rule in state.dynamic_rules
        if matches_condition(evaluation_state, rule.when)
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
    availability_operations: list[CallableActionAvailabilityOperation] = []
    override_rules = []
    active_rule_ids: list[str] = []

    for rule in resolve_active_dynamic_rules(state, at_time=at_time):
        override = rule.apply.object_overrides.get(object_id)
        if override is None:
            continue

        active_rule_ids.append(rule.rule_id)
        if override.visible_state:
            effective_object.visible_state.update(override.visible_state)
        if override.disabled_callable_actions:
            availability_operations.extend(
                CallableActionAvailabilityOperation(enabled=False, matcher=matcher.model_copy(deep=True))
                for matcher in override.disabled_callable_actions
            )
        if override.enabled_callable_actions:
            availability_operations.extend(
                CallableActionAvailabilityOperation(enabled=True, matcher=matcher.model_copy(deep=True))
                for matcher in override.enabled_callable_actions
            )
        if override.callable_action_overrides:
            override_rules.extend(rule.model_copy(deep=True) for rule in override.callable_action_overrides)

    filtered_definitions, disabled_routes = filter_callable_action_definitions(
        effective_object,
        availability_operations=availability_operations,
        override_rules=override_rules,
    )
    effective_object.callable_actions = filtered_definitions
    effective_object.actionable = effective_object.actionable or bool(filtered_definitions)

    return EffectiveObjectView(
        object=effective_object,
        disabled_routes=tuple(
            CallableActionMatcher(action_name=action_name, action_args=action_args)
            for action_name, action_args in disabled_routes
        ),
        active_rule_ids=tuple(active_rule_ids),
    )


def build_effective_action_effect(
    state: WorldState,
    object_id: str,
    action_name: str,
    *,
    action_args: dict[str, str] | None = None,
    at_time: int | None = None,
) -> ObjectActionEffect | None:
    effective_view = build_effective_object_view(state, object_id, at_time=at_time)
    if effective_view is None:
        return None
    resolved_action = resolve_callable_action(
        effective_view.object,
        action_name=action_name,
        action_args=dict(action_args or {}),
    )
    if resolved_action is None or isinstance(resolved_action, CallableActionResolutionError):
        return None
    return resolved_action.effect
