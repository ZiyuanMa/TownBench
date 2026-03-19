from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agents import (
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    RunConfig,
    RunItemStreamEvent,
    set_default_openai_api,
)
from agents.exceptions import MaxTurnsExceeded
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from baselines.base import (
    BaselineEpisodeResult,
    build_episode_initial_input,
    build_episode_result,
    resolve_episode_env,
)
from baselines.openai_agents.agent import build_openai_agent
from baselines.openai_agents.config import OpenAIAgentsConfig
from runtime.env import TownBenchEnv

TextDeltaHandler = Callable[[str], None]
EventHandler = Callable[[str], None]


def run_openai_agents_episode(
    *,
    scenario_path: str | Path | None = None,
    env: TownBenchEnv | None = None,
    config: OpenAIAgentsConfig | None = None,
    agent_cls: type | None = None,
    runner_cls: type | None = None,
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
    outcome = _run_sync_episode(prepared)
    return build_episode_result(env=prepared.env, final_output=outcome.final_output, runner_error=outcome.runner_error)


async def run_openai_agents_episode_streamed(
    *,
    scenario_path: str | Path | None = None,
    env: TownBenchEnv | None = None,
    config: OpenAIAgentsConfig | None = None,
    agent_cls: type | None = None,
    runner_cls: type | None = None,
    function_tool_decorator=None,
    on_text_delta: TextDeltaHandler | None = None,
    on_event: EventHandler | None = None,
) -> BaselineEpisodeResult:
    prepared = _prepare_episode_run(
        scenario_path=scenario_path,
        env=env,
        config=config,
        agent_cls=agent_cls,
        runner_cls=runner_cls,
        function_tool_decorator=function_tool_decorator,
    )
    outcome = await _run_streamed_episode(
        prepared,
        on_text_delta=on_text_delta,
        on_event=on_event,
    )
    return build_episode_result(env=prepared.env, final_output=outcome.final_output, runner_error=outcome.runner_error)


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


class _RunnerOutcome:
    def __init__(self, *, final_output: str, runner_error: str | None) -> None:
        self.final_output = final_output
        self.runner_error = runner_error


def _prepare_episode_run(
    *,
    scenario_path: str | Path | None,
    env: TownBenchEnv | None,
    config: OpenAIAgentsConfig | None,
    agent_cls: type | None,
    runner_cls: type | None,
    function_tool_decorator,
) -> _PreparedEpisodeRun:
    active_env = resolve_episode_env(scenario_path=scenario_path, env=env)
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
        initial_input=build_episode_initial_input(
            opening_briefing=active_env.state.opening_briefing,
            public_rules=active_env.state.public_rules,
            initial_observation=initial_observation.model_dump(),
        ),
        run_config=RunConfig(tracing_disabled=resolved_config.tracing_disabled),
    )


def _run_sync_episode(prepared: _PreparedEpisodeRun) -> _RunnerOutcome:
    runner_error: str | None = None
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
        runner_error = _resolve_runner_error(prepared.env, exc)
    return _RunnerOutcome(final_output=final_output, runner_error=runner_error)


async def _run_streamed_episode(
    prepared: _PreparedEpisodeRun,
    *,
    on_text_delta: TextDeltaHandler | None,
    on_event: EventHandler | None,
) -> _RunnerOutcome:
    runner_error: str | None = None
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
        runner_error = _resolve_runner_error(prepared.env, exc)

    return _RunnerOutcome(
        final_output=str(getattr(streamed_result, "final_output", "") or ""),
        runner_error=runner_error,
    )


def _resolve_runner_error(env: TownBenchEnv, exc: MaxTurnsExceeded) -> str | None:
    return None if env.is_done() else str(exc)


def _handle_stream_event(
    event: Any,
    *,
    on_text_delta: TextDeltaHandler | None,
    on_event: EventHandler | None,
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
