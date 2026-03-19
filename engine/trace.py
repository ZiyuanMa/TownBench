from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TraceEntry(BaseModel):
    step_id: int
    raw_action: dict[str, Any] = Field(default_factory=dict)
    normalized_action: dict[str, Any] = Field(default_factory=dict)
    success: bool
    error_type: str | None = None
    message: str
    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = Field(default_factory=dict)
    triggered_events: list[str] = Field(default_factory=list)
    observation_summary: dict[str, Any] = Field(default_factory=dict)
    done: bool = False
    termination_reason: str | None = None
