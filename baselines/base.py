from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from typing import Union

from pydantic import BaseModel, Field

from engine.trace import TraceEntry
from evaluation.scorer import EpisodeScore, score_episode
from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


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


def resolve_episode_env(
    *,
    scenario_path: Optional[Union[str, Path]],
    env: Optional[TownBenchEnv],
) -> TownBenchEnv:
    if env is not None:
        return env
    if scenario_path is None:
        raise ValueError("Provide either `scenario_path` or `env` when running a baseline episode.")
    return TownBenchEnv(load_scenario(scenario_path))


def build_episode_initial_input(
    *,
    opening_briefing: str,
    public_rules: list[str],
    initial_observation: dict[str, Any],
) -> str:
    observation_json = json.dumps(initial_observation, ensure_ascii=False, indent=2)
    sections = []
    if opening_briefing:
        sections.append(f"Opening briefing:\n{opening_briefing}")
    if public_rules:
        rules_block = "\n".join(f"- {rule}" for rule in public_rules)
        sections.append(f"Public rules:\n{rules_block}")
    sections.append(f"Initial observation:\n{observation_json}")
    return "\n\n".join(sections)


def build_episode_result(
    *,
    env: TownBenchEnv,
    final_output: str,
    runner_error: Optional[str],
) -> BaselineEpisodeResult:
    trace = env.get_trace()
    score = score_episode(trace, env.state)
    return BaselineEpisodeResult(
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
