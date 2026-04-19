from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from engine.state import ActionCost, WorldState

ActionType = Literal[
    "move_to",
    "inspect",
    "open_resource",
    "check_status",
    "call_action",
    "wait",
]


class Action(BaseModel):
    type: ActionType
    target_id: str | None = None
    action_name: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


PayloadBuilder = Callable[[WorldState], dict[str, Any]]


@dataclass
class ActionExecution:
    success: bool
    message: str
    error_type: str | None = None
    action_cost_override: ActionCost | None = None
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] | None = None
    agent_stat_deltas: dict[str, int] | None = None
    result_data: dict[str, Any] | None = None
    payload_builder: PayloadBuilder | None = None


ActionHandler = Callable[[WorldState, Action], ActionExecution]
