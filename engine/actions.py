from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

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
