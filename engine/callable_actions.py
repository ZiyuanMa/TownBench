from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from engine.state import (
    CallableActionDefinition,
    CallableActionMatcher,
    CallableActionRoute,
    ObjectActionEffect,
    WorldObject,
)


@dataclass(frozen=True)
class ResolvedCallableAction:
    action_name: str
    action_args: dict[str, str]
    effect: ObjectActionEffect


@dataclass(frozen=True)
class CallableActionResolutionError:
    error_type: str
    message: str
    data: dict[str, Any]


@dataclass(frozen=True)
class CallableActionAvailabilityOperation:
    enabled: bool
    matcher: CallableActionMatcher


def get_callable_action_definitions(world_object: WorldObject) -> dict[str, CallableActionDefinition]:
    return {
        action_name: definition.model_copy(deep=True)
        for action_name, definition in world_object.callable_actions.items()
    }


def build_callable_actions(world_object: WorldObject) -> list[dict[str, Any]]:
    callable_actions: list[dict[str, Any]] = []
    for action_name, definition in get_callable_action_definitions(world_object).items():
        arguments: list[dict[str, Any]] = []
        for argument_name, argument_spec in definition.arguments.items():
            available_values = {
                route.match.get(argument_name)
                for route in definition.routes
                if argument_name in route.match
            }
            options = [option for option in argument_spec.options if option in available_values]
            arguments.append(
                {
                    "name": argument_name,
                    "type": argument_spec.type,
                    "required": argument_spec.required,
                    "options": options,
                    "description": argument_spec.description,
                }
            )

        callable_actions.append(
            {
                "action_name": action_name,
                "description": definition.description,
                "arguments": arguments,
            }
        )
    return callable_actions


def resolve_callable_action(
    world_object: WorldObject,
    *,
    action_name: str,
    action_args: dict[str, Any],
) -> ResolvedCallableAction | CallableActionResolutionError | None:
    normalized_args = {key: str(value) for key, value in action_args.items()}
    definition = get_callable_action_definitions(world_object).get(action_name)
    if definition is None:
        return None

    declared_arguments = definition.arguments
    unknown_arguments = sorted(set(normalized_args) - set(declared_arguments))
    if unknown_arguments:
        return CallableActionResolutionError(
            error_type="invalid_action_args",
            message=f"Action `{action_name}` received unsupported action_args.",
            data={
                "requested_action": action_name,
                "requested_action_args": normalized_args,
                "invalid_action_arg_names": unknown_arguments,
            },
        )

    missing_arguments = sorted(
        argument_name
        for argument_name, argument_spec in declared_arguments.items()
        if argument_spec.required and argument_name not in normalized_args
    )
    if missing_arguments:
        return CallableActionResolutionError(
            error_type="missing_action_args",
            message=f"Action `{action_name}` requires action_args.",
            data={
                "requested_action": action_name,
                "requested_action_args": normalized_args,
                "missing_action_arg_names": missing_arguments,
            },
        )

    for argument_name, argument_spec in declared_arguments.items():
        if argument_name not in normalized_args:
            continue
        value = normalized_args[argument_name]
        if value not in argument_spec.options:
            return CallableActionResolutionError(
                error_type="invalid_action_args",
                message=f"Action `{action_name}` received unsupported action_args.",
                data={
                    "requested_action": action_name,
                    "requested_action_args": normalized_args,
                    "invalid_action_arg_names": [argument_name],
                },
            )

    for route in definition.routes:
        if route.match == normalized_args:
            return ResolvedCallableAction(
                action_name=action_name,
                action_args=normalized_args,
                effect=route.effect.model_copy(deep=True),
            )

    return CallableActionResolutionError(
        error_type="invalid_action_args",
        message=f"Action `{action_name}` received unsupported action_args.",
        data={
            "requested_action": action_name,
            "requested_action_args": normalized_args,
        },
    )


def list_callable_action_names(world_object: WorldObject) -> list[str]:
    return [item["action_name"] for item in build_callable_actions(world_object)]


def matches_callable_action_matcher(
    action_name: str,
    action_args: dict[str, str],
    matcher: CallableActionMatcher,
) -> bool:
    if action_name != matcher.action_name:
        return False
    return all(action_args.get(key) == value for key, value in matcher.action_args.items())


def filter_callable_action_definitions(
    world_object: WorldObject,
    *,
    availability_operations: list[CallableActionAvailabilityOperation],
    override_rules,
) -> tuple[dict[str, CallableActionDefinition], list[tuple[str, dict[str, str]]]]:
    definitions = get_callable_action_definitions(world_object)
    filtered_definitions: dict[str, CallableActionDefinition] = {}
    disabled_routes: list[tuple[str, dict[str, str]]] = []

    for action_name, definition in definitions.items():
        filtered_routes: list[CallableActionRoute] = []
        for route in definition.routes:
            enabled = True
            for operation in availability_operations:
                if matches_callable_action_matcher(action_name, route.match, operation.matcher):
                    enabled = operation.enabled

            if not enabled:
                disabled_routes.append((action_name, dict(route.match)))
                continue

            effective_effect = route.effect.model_copy(deep=True)
            for override_rule in override_rules:
                if matches_callable_action_matcher(action_name, route.match, override_rule.match):
                    effective_effect = apply_action_effect_override(
                        effective_effect,
                        override_rule.override,
                    )
            filtered_routes.append(
                CallableActionRoute(match=deepcopy(route.match), effect=effective_effect)
            )

        if not filtered_routes:
            continue

        filtered_definitions[action_name] = CallableActionDefinition(
            description=definition.description,
            arguments={name: spec.model_copy(deep=True) for name, spec in definition.arguments.items()},
            routes=filtered_routes,
        )

    return filtered_definitions, disabled_routes


def apply_action_effect_override(
    base_effect: ObjectActionEffect,
    effect_override,
) -> ObjectActionEffect:
    updated_effect = base_effect.model_copy(deep=True)
    override_data = effect_override.model_dump(exclude_none=True)
    for field_name, value in override_data.items():
        setattr(updated_effect, field_name, value)
    return updated_effect
