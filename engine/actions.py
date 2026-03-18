from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Callable, Literal, Optional, Union

from pydantic import BaseModel, Field

from engine.state import ActionCost

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
    ),
    ActionSpec(
        action_type="search",
        default_cost=ActionCost(time_delta=2, energy_delta=-1),
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
    ),
    ActionSpec(
        action_type="check_status",
        tool=ActionToolSpec(
            name="check_status",
            description="Check the agent status, including location, money, energy, inventory and notes.",
            parameters=(),
            build_action=_build_check_status_action,
        ),
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
    ),
)


ACTION_SPECS: dict[str, ActionSpec] = {spec.action_type: spec for spec in _ACTION_SPEC_LIST}
TOOL_ACTION_SPECS: tuple[ActionSpec, ...] = tuple(spec for spec in _ACTION_SPEC_LIST if spec.tool is not None)


def get_action_spec(action_type: str) -> Optional[ActionSpec]:
    return ACTION_SPECS.get(action_type)
