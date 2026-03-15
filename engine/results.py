from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from engine.observation import Observation


class StepResult(BaseModel):
    success: bool
    observation: Observation
    message: str
    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = Field(default_factory=dict)
    triggered_events: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    done: bool = False
    termination_reason: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
