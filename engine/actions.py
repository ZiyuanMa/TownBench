from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from engine.action_handlers import (
    _handle_call_action,
    _handle_check_status,
    _handle_inspect,
    _handle_load_skill,
    _handle_move_to,
    _handle_open_resource,
    _handle_write_note,
)
from engine.action_models import Action, ActionExecution, ActionHandler, ActionType
from engine.rules import apply_state_delta
from engine.state import ActionCost, WorldState


def normalize_action(value: Action | dict[str, Any]) -> Action:
    if isinstance(value, Action):
        return value
    return Action.model_validate(value)


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
    tool: ActionToolSpec | None = None
    handler: ActionHandler | None = None


_ACTION_SPEC_LIST: tuple[ActionSpec, ...] = (
    ActionSpec(
        action_type="move_to",
        default_cost=ActionCost(time_delta=10, energy_delta=-2),
        tool=ActionToolSpec(
            name="move_to",
            description="Move the agent to a linked location by location id.",
            parameters=(ActionToolParameter("target_id"),),
            build_action=lambda target_id: Action(type="move_to", target_id=target_id),
        ),
        handler=_handle_move_to,
    ),
    ActionSpec(
        action_type="inspect",
        default_cost=ActionCost(time_delta=4, energy_delta=-1),
        tool=ActionToolSpec(
            name="inspect",
            description="Inspect the current location or an object that is present there.",
            parameters=(ActionToolParameter("target_id"),),
            build_action=lambda target_id: Action(type="inspect", target_id=target_id),
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
            build_action=lambda target_id: Action(type="open_resource", target_id=target_id),
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
            build_action=lambda target_id: Action(type="load_skill", target_id=target_id),
        ),
        handler=_handle_load_skill,
    ),
    ActionSpec(
        action_type="check_status",
        tool=ActionToolSpec(
            name="check_status",
            description="Check the agent status, including location, money, energy, inventory and notes.",
            parameters=(),
            build_action=lambda: Action(type="check_status"),
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
            build_action=lambda text: Action(type="write_note", args={"text": text}),
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
            build_action=lambda target_id, action_name: Action(
                type="call_action", target_id=target_id, args={"action": action_name}
            ),
        ),
        handler=_handle_call_action,
    ),
)


ACTION_SPECS: dict[str, ActionSpec] = {spec.action_type: spec for spec in _ACTION_SPEC_LIST}
TOOL_ACTION_SPECS: tuple[ActionSpec, ...] = tuple(spec for spec in _ACTION_SPEC_LIST if spec.tool is not None)


def get_action_spec(action_type: str) -> ActionSpec | None:
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
