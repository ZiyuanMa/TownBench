from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Optional, Union

from agents import (
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    RunConfig,
    RunItemStreamEvent,
    set_default_openai_api,
)
from agents.exceptions import MaxTurnsExceeded
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from baselines.base import BaselineEpisodeResult
from baselines.openai_agents.agent import build_openai_agent
from baselines.openai_agents.config import OpenAIAgentsConfig
from evaluation.scorer import score_episode
from runtime.env import TownBenchEnv
from scenario.loader import load_scenario

TextDeltaHandler = Callable[[str], None]
EventHandler = Callable[[str], None]


def run_openai_agents_episode(
    *,
    scenario_path: Optional[Union[str, Path]] = None,
    env: Optional[TownBenchEnv] = None,
    config: Optional[OpenAIAgentsConfig] = None,
    agent_cls: Optional[type] = None,
    runner_cls: Optional[type] = None,
    function_tool_decorator=None,
) -> BaselineEpisodeResult:
    prepared = _prepare_episode_run(
        scenario_path=scenario_path,
        env=env,
        config=config,
        agent_cls=agent_cls,
        runner_cls=runner_cls,
        function_tool_decorator=function_tool_decorator,
    )
    runner_error: Optional[str] = None
    final_output = ""
    try:
        run_result = prepared.runner_type.run_sync(
            prepared.agent,
            prepared.initial_input,
            max_turns=prepared.config.max_turns,
            run_config=prepared.run_config,
        )
        final_output = str(getattr(run_result, "final_output", ""))
    except MaxTurnsExceeded as exc:
        runner_error = None if prepared.env.is_done() else str(exc)
        final_output = ""
    return _build_episode_result(
        env=prepared.env,
        final_output=final_output,
        runner_error=runner_error,
    )


async def run_openai_agents_episode_streamed(
    *,
    scenario_path: Optional[Union[str, Path]] = None,
    env: Optional[TownBenchEnv] = None,
    config: Optional[OpenAIAgentsConfig] = None,
    agent_cls: Optional[type] = None,
    runner_cls: Optional[type] = None,
    function_tool_decorator=None,
    on_text_delta: Optional[TextDeltaHandler] = None,
    on_event: Optional[EventHandler] = None,
) -> BaselineEpisodeResult:
    prepared = _prepare_episode_run(
        scenario_path=scenario_path,
        env=env,
        config=config,
        agent_cls=agent_cls,
        runner_cls=runner_cls,
        function_tool_decorator=function_tool_decorator,
    )
    runner_error: Optional[str] = None
    streamed_result = prepared.runner_type.run_streamed(
        prepared.agent,
        prepared.initial_input,
        max_turns=prepared.config.max_turns,
        run_config=prepared.run_config,
    )
    try:
        async for event in streamed_result.stream_events():
            _handle_stream_event(event, on_text_delta=on_text_delta, on_event=on_event)
    except MaxTurnsExceeded as exc:
        runner_error = None if prepared.env.is_done() else str(exc)

    final_output = str(getattr(streamed_result, "final_output", "") or "")
    return _build_episode_result(
        env=prepared.env,
        final_output=final_output,
        runner_error=runner_error,
    )


def _build_env(scenario_path: Optional[Union[str, Path]]) -> TownBenchEnv:
    if scenario_path is None:
        raise ValueError("Provide either `scenario_path` or `env` when running the OpenAI baseline.")
    return TownBenchEnv(load_scenario(scenario_path))


def _build_initial_input(
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


def _load_runner_class() -> type:
    try:
        from agents import Runner
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI baseline."
        ) from exc
    return Runner


class _PreparedEpisodeRun:
    def __init__(
        self,
        *,
        env: TownBenchEnv,
        config: OpenAIAgentsConfig,
        agent: Any,
        runner_type: type,
        initial_input: str,
        run_config: RunConfig,
    ) -> None:
        self.env = env
        self.config = config
        self.agent = agent
        self.runner_type = runner_type
        self.initial_input = initial_input
        self.run_config = run_config


def _prepare_episode_run(
    *,
    scenario_path: Optional[Union[str, Path]],
    env: Optional[TownBenchEnv],
    config: Optional[OpenAIAgentsConfig],
    agent_cls: Optional[type],
    runner_cls: Optional[type],
    function_tool_decorator,
) -> _PreparedEpisodeRun:
    active_env = env or _build_env(scenario_path)
    initial_observation = active_env.reset()
    resolved_config = config or OpenAIAgentsConfig.from_env()
    set_default_openai_api(resolved_config.api)
    agent = build_openai_agent(
        active_env,
        resolved_config,
        agent_cls=agent_cls,
        function_tool_decorator=function_tool_decorator,
    )
    runner_type = runner_cls or _load_runner_class()
    return _PreparedEpisodeRun(
        env=active_env,
        config=resolved_config,
        agent=agent,
        runner_type=runner_type,
        initial_input=_build_initial_input(
            opening_briefing=active_env.state.opening_briefing,
            public_rules=active_env.state.public_rules,
            initial_observation=initial_observation.model_dump(),
        ),
        run_config=RunConfig(tracing_disabled=resolved_config.tracing_disabled),
    )


def _build_episode_result(
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


def _handle_stream_event(
    event: Any,
    *,
    on_text_delta: Optional[TextDeltaHandler],
    on_event: Optional[EventHandler],
) -> None:
    if isinstance(event, RawResponsesStreamEvent):
        data = event.data
        if isinstance(data, ResponseTextDeltaEvent):
            if on_text_delta and data.delta:
                on_text_delta(data.delta)
            return
        delta = getattr(data, "delta", None)
        if on_text_delta and isinstance(delta, str) and delta:
            on_text_delta(delta)
        return

    if isinstance(event, RunItemStreamEvent):
        if on_event is None:
            return
        if event.item.type == "tool_call_item":
            on_event("tool_called")
        elif event.item.type == "tool_call_output_item":
            on_event(f"tool_output: {event.item.output}")
        return

    if isinstance(event, AgentUpdatedStreamEvent) and on_event is not None:
        on_event(f"agent_updated: {event.new_agent.name}")
