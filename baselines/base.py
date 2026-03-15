from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from engine.trace import TraceEntry
from evaluation.scorer import EpisodeScore


class BaselineEpisodeResult(BaseModel):
    scenario_id: str
    opening_briefing: str
    public_rules: list[str] = Field(default_factory=list)
    final_output: str
    runner_error: Optional[str] = None
    score: EpisodeScore
    trace: list[TraceEntry] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)
    final_observation: dict[str, Any] = Field(default_factory=dict)
    done: bool = False
    termination_reason: Optional[str] = None
