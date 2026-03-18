from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Union

from pydantic import BaseModel, Field

from engine.rules import apply_state_delta, matches_world_flags
from engine.state import ActionCost, WorldObject, WorldState

ActionType = Literal[
    "move_to",
    "search",
    "inspect",
    "open_resource",
    "load_skill",
    "check_status",
    "write_note",
    "call_action",
]


class Action(BaseModel):
    type: ActionType
    target_id: Optional[str] = None
    args: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_action(value: Union[Action, Mapping[str, Any]]) -> Action:
    if isinstance(value, Action):
        return value
    return Action.model_validate(value)


PayloadBuilder = Callable[[WorldState], dict[str, Any]]


@dataclass
class ActionExecution:
    success: bool
    message: str
    error_type: Optional[str] = None
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] | None = None
    payload_builder: Optional[PayloadBuilder] = None


ActionHandler = Callable[[WorldState, Action], ActionExecution]
ActionToolBuilder = Callable[..., Action]


@dataclass(frozen=True)
class ActionToolParameter:
    name: str
    annotation: Any = str


@dataclass(frozen=True)
class ActionToolSpec:
    name: str
    description: str
    parameters: tuple[ActionToolParameter, ...]
    build_action: ActionToolBuilder


@dataclass(frozen=True)
class ActionSpec:
    action_type: ActionType
    default_cost: ActionCost = field(default_factory=ActionCost)
    tool: Optional[ActionToolSpec] = None
    handler: Optional[ActionHandler] = None


def _success(
    message: str,
    *,
    payload_builder: Optional[PayloadBuilder] = None,
    money_delta: int = 0,
    energy_delta: int = 0,
    inventory_delta: Optional[dict[str, int]] = None,
) -> ActionExecution:
    return ActionExecution(
        success=True,
        message=message,
        payload_builder=payload_builder,
        money_delta=money_delta,
        energy_delta=energy_delta,
        inventory_delta=dict(inventory_delta or {}),
    )


def _failure(error_type: str, message: str) -> ActionExecution:
    return ActionExecution(success=False, message=message, error_type=error_type)


def _build_move_to_action(target_id: str) -> Action:
    return Action(type="move_to", target_id=target_id)


def _build_inspect_action(target_id: str) -> Action:
    return Action(type="inspect", target_id=target_id)


def _build_open_resource_action(target_id: str) -> Action:
    return Action(type="open_resource", target_id=target_id)


def _build_load_skill_action(target_id: str) -> Action:
    return Action(type="load_skill", target_id=target_id)


def _build_check_status_action() -> Action:
    return Action(type="check_status")


def _build_write_note_action(text: str) -> Action:
    return Action(type="write_note", args={"text": text})


def _build_call_action(target_id: str, action_name: str) -> Action:
    return Action(type="call_action", target_id=target_id, args={"action": action_name})


def _handle_check_status(state: WorldState, action: Action) -> ActionExecution:
    del action
    return _success(
        "Status checked.",
        payload_builder=lambda current_state: {"agent_status": _serialize_agent_status(current_state)},
    )


def _handle_move_to(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "move_to requires a target_id.")

    current_location = state.locations[state.agent.location_id]
    if action.target_id not in state.locations:
        return _failure("unknown_location", f"Unknown location `{action.target_id}`.")
    if action.target_id not in current_location.links:
        return _failure("unreachable_location", f"Location `{action.target_id}` is not reachable.")

    state.agent.location_id = action.target_id
    target_location = state.locations[action.target_id]
    return _success(f"Moved to `{target_location.name}`.")


def _handle_inspect(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "inspect requires a target_id.")

    current_location = state.locations[state.agent.location_id]
    if action.target_id == current_location.location_id:
        return _success(
            f"Inspected location `{current_location.name}`.",
            payload_builder=lambda current_state, location_id=current_location.location_id: {
                "kind": "location",
                "location": current_state.locations[location_id].model_dump(),
            },
        )

    world_object = _get_accessible_object(state, action.target_id)
    if isinstance(world_object, ActionExecution):
        return world_object
    if not world_object.inspectable:
        return _failure("not_inspectable", f"Target `{action.target_id}` cannot be inspected.")

    return _success(
        f"Inspected object `{world_object.name}`.",
        payload_builder=lambda current_state, object_id=world_object.object_id: {
            "kind": "object",
            "object": _serialize_object(current_state.objects[object_id]),
        },
    )


def _handle_write_note(state: WorldState, action: Action) -> ActionExecution:
    text = str(action.args.get("text", "")).strip()
    if not text:
        return _failure("missing_text", "write_note requires non-empty `args.text`.")

    state.agent.notes.append(text)
    return _success("Note saved.")


def _handle_search(state: WorldState, action: Action) -> ActionExecution:
    del state, action
    return _failure("disabled_action", "search is intentionally disabled in the current milestone.")


def _handle_open_resource(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "open_resource requires a target_id.")

    world_object = _get_accessible_object(state, action.target_id)
    if isinstance(world_object, ActionExecution):
        return world_object
    if not world_object.readable or not world_object.resource_content:
        return _failure("not_readable", f"Target `{action.target_id}` is not a readable resource.")

    return _success(
        f"Opened resource `{world_object.name}`.",
        payload_builder=lambda current_state, object_id=world_object.object_id: {
            "kind": "resource",
            "object_id": object_id,
            "title": current_state.objects[object_id].name,
            "content": current_state.objects[object_id].resource_content,
        },
    )


def _handle_load_skill(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "load_skill requires a target_id.")

    skill = state.skills.get(action.target_id)
    if skill is None:
        return _failure("unknown_skill", f"Unknown skill `{action.target_id}`.")

    return _success(
        f"Loaded skill `{skill.name}`.",
        payload_builder=lambda current_state, skill_id=skill.skill_id: {
            "kind": "skill",
            "skill_id": skill_id,
            "name": current_state.skills[skill_id].name,
            "description": current_state.skills[skill_id].description,
            "content": current_state.skills[skill_id].content,
        },
    )


def _handle_call_action(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "call_action requires a target_id.")

    action_name = str(action.args.get("action", "")).strip()
    if not action_name:
        return _failure("missing_action_name", "call_action requires `args.action`.")

    world_object = _get_accessible_object(state, action.target_id)
    if isinstance(world_object, ActionExecution):
        return world_object
    if not world_object.actionable:
        return _failure("not_actionable", f"Target `{action.target_id}` does not support actions.")
    if action_name not in world_object.action_ids:
        return _failure(
            "action_not_exposed",
            f"Action `{action_name}` is not exposed on `{action.target_id}` in the current location.",
        )

    effect = world_object.action_effects.get(action_name)
    if effect is None:
        return _failure(
            "unknown_object_action",
            f"Target `{action.target_id}` does not support `{action_name}`.",
        )
    if not matches_world_flags(state.world_flags, effect.required_world_flags):
        return _failure(
            "missing_prerequisites",
            f"Action `{action_name}` on `{action.target_id}` is not available in the current world state.",
        )
    if not _has_required_inventory(state, effect.required_inventory):
        return _failure(
            "missing_inventory",
            f"Action `{action_name}` on `{action.target_id}` requires inventory items that are not available.",
        )
    if state.agent.money < effect.required_money:
        return _failure(
            "insufficient_money",
            f"Action `{action_name}` on `{action.target_id}` requires at least {effect.required_money} money.",
        )
    if state.agent.money + effect.money_delta < 0:
        return _failure(
            "insufficient_money",
            f"Action `{action_name}` on `{action.target_id}` would reduce money below zero.",
        )
    if not _can_apply_inventory_delta(state, effect.inventory_delta):
        return _failure(
            "insufficient_inventory",
            f"Action `{action_name}` on `{action.target_id}` would reduce inventory below zero.",
        )
    if effect.move_to_location_id and effect.move_to_location_id not in state.locations:
        return _failure(
            "unknown_location",
            f"Action `{action_name}` on `{action.target_id}` references unknown location `{effect.move_to_location_id}`.",
        )

    world_object.visible_state.update(effect.set_visible_state)
    state.world_flags.update(effect.set_world_flags)
    apply_state_delta(
        state,
        ActionCost(
            money_delta=effect.money_delta,
            energy_delta=effect.energy_delta,
            inventory_delta=effect.inventory_delta,
        ),
    )
    if effect.move_to_location_id:
        state.agent.location_id = effect.move_to_location_id
    return _success(
        effect.message,
        payload_builder=lambda current_state, object_id=world_object.object_id, action_name=action_name: {
            "kind": "action",
            "object_id": object_id,
            "action": action_name,
            "visible_state": deepcopy(current_state.objects[object_id].visible_state),
            "world_flags": dict(current_state.world_flags),
            "money": current_state.agent.money,
            "energy": current_state.agent.energy,
            "inventory": dict(current_state.agent.inventory),
            "location_id": current_state.agent.location_id,
        },
        money_delta=effect.money_delta,
        energy_delta=effect.energy_delta,
        inventory_delta=effect.inventory_delta,
    )


def _get_accessible_object(state: WorldState, target_id: str) -> WorldObject | ActionExecution:
    current_location = state.locations[state.agent.location_id]
    world_object = state.objects.get(target_id)
    if world_object is None:
        return _failure("unknown_target", f"Unknown target `{target_id}`.")
    if world_object.location_id != current_location.location_id:
        return _failure("not_accessible", f"Target `{target_id}` is not in the current location.")
    return world_object


def _serialize_object(world_object: WorldObject) -> dict[str, Any]:
    return {
        "object_id": world_object.object_id,
        "name": world_object.name,
        "object_type": world_object.object_type,
        "summary": world_object.summary,
        "visible_state": deepcopy(world_object.visible_state),
        "action_ids": list(world_object.action_ids),
    }


def _serialize_agent_status(state: WorldState) -> dict[str, Any]:
    return {
        "current_time": state.current_time,
        "location_id": state.agent.location_id,
        "money": state.agent.money,
        "energy": state.agent.energy,
        "inventory": dict(state.agent.inventory),
        "notes": list(state.agent.notes),
        "status_effects": list(state.agent.status_effects),
    }


def _has_required_inventory(state: WorldState, required_inventory: dict[str, int]) -> bool:
    return all(state.agent.inventory.get(item_id, 0) >= required for item_id, required in required_inventory.items())


def _can_apply_inventory_delta(state: WorldState, inventory_delta: dict[str, int]) -> bool:
    for item_id, delta in inventory_delta.items():
        if state.agent.inventory.get(item_id, 0) + delta < 0:
            return False
    return True


_ACTION_SPEC_LIST: tuple[ActionSpec, ...] = (
    ActionSpec(
        action_type="move_to",
        default_cost=ActionCost(time_delta=10, energy_delta=-2),
        tool=ActionToolSpec(
            name="move_to",
            description="Move the agent to a linked location by location id.",
            parameters=(ActionToolParameter("target_id"),),
            build_action=_build_move_to_action,
        ),
        handler=_handle_move_to,
    ),
    ActionSpec(
        action_type="search",
        default_cost=ActionCost(time_delta=2, energy_delta=-1),
        handler=_handle_search,
    ),
    ActionSpec(
        action_type="inspect",
        default_cost=ActionCost(time_delta=4, energy_delta=-1),
        tool=ActionToolSpec(
            name="inspect",
            description="Inspect the current location or an object that is present there.",
            parameters=(ActionToolParameter("target_id"),),
            build_action=_build_inspect_action,
        ),
        handler=_handle_inspect,
    ),
    ActionSpec(
        action_type="open_resource",
        default_cost=ActionCost(time_delta=3),
        tool=ActionToolSpec(
            name="open_resource",
            description="Open a readable resource in the current location and return its content.",
            parameters=(ActionToolParameter("target_id"),),
            build_action=_build_open_resource_action,
        ),
        handler=_handle_open_resource,
    ),
    ActionSpec(
        action_type="load_skill",
        default_cost=ActionCost(time_delta=5, energy_delta=-1),
        tool=ActionToolSpec(
            name="load_skill",
            description="Load a skill document by skill id and return its full content.",
            parameters=(ActionToolParameter("target_id"),),
            build_action=_build_load_skill_action,
        ),
        handler=_handle_load_skill,
    ),
    ActionSpec(
        action_type="check_status",
        tool=ActionToolSpec(
            name="check_status",
            description="Check the agent status, including location, money, energy, inventory and notes.",
            parameters=(),
            build_action=_build_check_status_action,
        ),
        handler=_handle_check_status,
    ),
    ActionSpec(
        action_type="write_note",
        default_cost=ActionCost(time_delta=1),
        tool=ActionToolSpec(
            name="write_note",
            description="Write a note into the agent's notebook.",
            parameters=(ActionToolParameter("text"),),
            build_action=_build_write_note_action,
        ),
        handler=_handle_write_note,
    ),
    ActionSpec(
        action_type="call_action",
        default_cost=ActionCost(time_delta=8, energy_delta=-3),
        tool=ActionToolSpec(
            name="call_action",
            description="Call an exposed action on an object in the current location.",
            parameters=(ActionToolParameter("target_id"), ActionToolParameter("action_name")),
            build_action=_build_call_action,
        ),
        handler=_handle_call_action,
    ),
)


ACTION_SPECS: dict[str, ActionSpec] = {spec.action_type: spec for spec in _ACTION_SPEC_LIST}
TOOL_ACTION_SPECS: tuple[ActionSpec, ...] = tuple(spec for spec in _ACTION_SPEC_LIST if spec.tool is not None)


def get_action_spec(action_type: str) -> Optional[ActionSpec]:
    return ACTION_SPECS.get(action_type)


def get_action_cost(state: WorldState, action_type: str) -> ActionCost:
    override = state.action_costs.get(action_type)
    if override is not None:
        return override.model_copy(deep=True)
    spec = get_action_spec(action_type)
    if spec is not None:
        return spec.default_cost.model_copy(deep=True)
    return ActionCost()


def apply_action_costs(state: WorldState, action_type: str) -> ActionCost:
    return apply_state_delta(state, get_action_cost(state, action_type))
