from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.trace import TraceEntry
from evaluation.scorer import EpisodeScore, score_episode
from runtime.env import TownBenchEnv


class EpisodeRunResult(BaseModel):
    scenario_id: str
    opening_briefing: str
    public_rules: list[str] = Field(default_factory=list)
    final_output: str
    runner_error: str | None = None
    score: EpisodeScore
    trace: list[TraceEntry] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)
    final_observation: dict[str, Any] = Field(default_factory=dict)
    done: bool = False
    termination_reason: str | None = None


def build_episode_result(
    *,
    env: TownBenchEnv,
    final_output: str,
    runner_error: str | None,
) -> EpisodeRunResult:
    trace = env.get_trace()
    score = score_episode(trace, env.state)
    return EpisodeRunResult(
        scenario_id=env.state.scenario_id,
        opening_briefing=env.state.opening_briefing,
        public_rules=list(env.state.public_rules),
        final_output=final_output,
        runner_error=runner_error,
        score=score,
        trace=trace,
        final_state=env.state.model_dump(),
        final_observation=env.get_observation().model_dump(),
        done=score.done,
        termination_reason=score.termination_reason,
    )
