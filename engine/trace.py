from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TraceEntry(BaseModel):
    step_id: int
    raw_action: dict[str, Any] = Field(default_factory=dict)
    normalized_action: dict[str, Any] = Field(default_factory=dict)
    success: bool
    error_type: Optional[str] = None
    message: str
    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    triggered_events: list[str] = Field(default_factory=list)
    observation_summary: dict[str, Any] = Field(default_factory=dict)
    done: bool = False
    termination_reason: Optional[str] = None
