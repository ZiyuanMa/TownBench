from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from engine.rendering import render_initial_observation
from evaluation.results import EpisodeRunResult, build_episode_result
from runtime.env import TownBenchEnv
from runtime.episode import build_episode_initial_input, resolve_episode_env
from townbench_agents.message_capture import (
    extract_openai_messages,
    extract_openai_messages_from_exception,
)
from townbench_agents.openai.agent import build_openai_agent
from townbench_agents.openai.config import OpenAIAgentConfig

TextDeltaHandler = Callable[[str], None]
EventHandler = Callable[[str], None]


def run_openai_agent_episode(
    *,
    scenario_path: str | Path | None = None,
    env: TownBenchEnv | None = None,
    config: OpenAIAgentConfig | None = None,
    build_agent_fn: Callable[..., Any] | None = None,
    runner: Any | None = None,
    agent_factory: Callable[..., Any] | None = None,
    model_settings_factory: Callable[..., Any] | None = None,
    tool_factory=None,
) -> EpisodeRunResult:
    prepared = _prepare_episode_run(
        scenario_path=scenario_path,
        env=env,
        config=config,
        build_agent_fn=build_agent_fn,
        runner=runner,
        agent_factory=agent_factory,
        model_settings_factory=model_settings_factory,
        tool_factory=tool_factory,
    )
    outcome = _run_sync_episode(prepared)
    return build_episode_result(
        env=prepared.env,
        final_output=outcome.final_output,
        runner_error=outcome.runner_error,
        messages=outcome.messages,
    )


async def run_openai_agent_episode_streamed(
    *,
    scenario_path: str | Path | None = None,
    env: TownBenchEnv | None = None,
    config: OpenAIAgentConfig | None = None,
    build_agent_fn: Callable[..., Any] | None = None,
    runner: Any | None = None,
    agent_factory: Callable[..., Any] | None = None,
    model_settings_factory: Callable[..., Any] | None = None,
    tool_factory=None,
    on_text_delta: TextDeltaHandler | None = None,
    on_event: EventHandler | None = None,
) -> EpisodeRunResult:
    prepared = _prepare_episode_run(
        scenario_path=scenario_path,
        env=env,
        config=config,
        build_agent_fn=build_agent_fn,
        runner=runner,
        agent_factory=agent_factory,
        model_settings_factory=model_settings_factory,
        tool_factory=tool_factory,
    )
    outcome = await _run_streamed_episode(
        prepared,
        on_text_delta=on_text_delta,
        on_event=on_event,
    )
    return build_episode_result(
        env=prepared.env,
        final_output=outcome.final_output,
        runner_error=outcome.runner_error,
        messages=outcome.messages,
    )


class _PreparedEpisodeRun:
    def __init__(
        self,
        *,
        env: TownBenchEnv,
        config: OpenAIAgentConfig,
        agent: Any,
        agent_input: str,
        runner: Any,
        run_config: Any,
    ) -> None:
        self.env = env
        self.config = config
        self.agent = agent
        self.agent_input = agent_input
        self.runner = runner
        self.run_config = run_config


class _RunnerOutcome:
    def __init__(
        self,
        *,
        final_output: str,
        runner_error: str | None,
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        self.final_output = final_output
        self.runner_error = runner_error
        self.messages = list(messages or [])


def _prepare_episode_run(
    *,
    scenario_path: str | Path | None,
    env: TownBenchEnv | None,
    config: OpenAIAgentConfig | None,
    build_agent_fn: Callable[..., Any] | None,
    runner: Any | None,
    agent_factory: Callable[..., Any] | None,
    model_settings_factory: Callable[..., Any] | None,
    tool_factory,
) -> _PreparedEpisodeRun:
    active_env = resolve_episode_env(scenario_path=scenario_path, env=env)
    initial_observation = active_env.reset()
    resolved_config = config or OpenAIAgentConfig.from_env()
    agent_builder = build_agent_fn or build_openai_agent
    agent = agent_builder(
        active_env,
        resolved_config,
        agent_factory=agent_factory,
        model_settings_factory=model_settings_factory,
        tool_factory=tool_factory,
    )
    agent_input = build_episode_initial_input(
        opening_briefing=active_env.state.opening_briefing,
        public_rules=active_env.state.public_rules,
        initial_observation=render_initial_observation(initial_observation),
    )
    return _PreparedEpisodeRun(
        env=active_env,
        config=resolved_config,
        agent=agent,
        agent_input=agent_input,
        runner=runner or _load_runner(),
        run_config=_build_run_config(resolved_config),
    )


def _run_sync_episode(prepared: _PreparedEpisodeRun) -> _RunnerOutcome:
    runner_error: str | None = None
    final_output = ""
    messages: list[dict[str, Any]] = []
    try:
        result = prepared.runner.run_sync(
            prepared.agent,
            prepared.agent_input,
            max_turns=prepared.config.max_turns or 10,
            run_config=prepared.run_config,
        )
        final_output = _extract_final_output(result)
        messages = extract_openai_messages(result, model=prepared.config.model)
    except Exception as exc:  # pragma: no cover - exercised by tests via fake exception
        if not _is_max_turns_error(exc):
            raise
        runner_error = _resolve_runner_error(prepared.env, exc)
        messages = extract_openai_messages_from_exception(exc, model=prepared.config.model)
    return _RunnerOutcome(final_output=final_output, runner_error=runner_error, messages=messages)


async def _run_streamed_episode(
    prepared: _PreparedEpisodeRun,
    *,
    on_text_delta: TextDeltaHandler | None,
    on_event: EventHandler | None,
) -> _RunnerOutcome:
    text_fragments: list[str] = []
    runner_error: str | None = None
    result = None
    messages: list[dict[str, Any]] = []
    try:
        result = prepared.runner.run_streamed(
            prepared.agent,
            prepared.agent_input,
            max_turns=prepared.config.max_turns or 10,
            run_config=prepared.run_config,
        )
        async for event in result.stream_events():
            delta = _handle_stream_event(event, on_text_delta=on_text_delta, on_event=on_event)
            if delta:
                text_fragments.append(delta)
    except Exception as exc:  # pragma: no cover - exercised by tests via fake exception
        if not _is_max_turns_error(exc):
            raise
        runner_error = _resolve_runner_error(prepared.env, exc)
        messages = extract_openai_messages_from_exception(exc, model=prepared.config.model)

    final_output = "".join(text_fragments)
    if not final_output and result is not None:
        final_output = _extract_final_output(result)
    if result is not None:
        result_messages = extract_openai_messages(result, model=prepared.config.model)
        if result_messages:
            messages = result_messages
    return _RunnerOutcome(final_output=final_output, runner_error=runner_error, messages=messages)


def _handle_stream_event(
    event: Any,
    *,
    on_text_delta: TextDeltaHandler | None,
    on_event: EventHandler | None,
) -> str:
    event_type = _get_value(event, "type")
    if event_type == "raw_response_event":
        delta = _extract_raw_text_delta(_get_value(event, "data"))
        if delta and on_text_delta is not None:
            on_text_delta(delta)
        return delta

    if event_type != "run_item_stream_event":
        return ""

    event_name = _get_value(event, "name")
    item = _get_value(event, "item")
    item_type = _get_value(item, "type")
    if (event_name == "tool_called" or item_type == "tool_call_item") and on_event is not None:
        on_event("tool_called")
    elif (event_name == "tool_output" or item_type == "tool_call_output_item") and on_event is not None:
        on_event(f"tool_output: {_extract_tool_output(item)}")
    return ""


def _extract_raw_text_delta(data: Any) -> str:
    delta = _get_value(data, "delta")
    if isinstance(delta, str):
        return delta
    return ""


def _extract_tool_output(item: Any) -> str:
    output = _get_value(item, "output")
    if output is None:
        return str(item)
    return str(output)


def _extract_final_output(result: Any) -> str:
    final_output = getattr(result, "final_output", None)
    if isinstance(final_output, str):
        return final_output
    if isinstance(result, dict):
        final_output = result.get("final_output")
        if isinstance(final_output, str):
            return final_output
    return str(result or "")


def _get_value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _build_run_config(config: OpenAIAgentConfig) -> Any:
    try:
        from agents import OpenAIProvider, RunConfig
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI Agents baseline."
        ) from exc

    uses_deepseek = _uses_deepseek_compatible_endpoint(config)
    kwargs: dict[str, Any] = {"tracing_disabled": config.tracing_disabled or uses_deepseek}
    if uses_deepseek:
        # DeepSeek thinking-mode chat completions require every historical tool-call assistant
        # message to include its original reasoning_content. The Agents SDK gives converted
        # reasoning items a shared placeholder ID, so omitting reasoning IDs prevents turn-history
        # deduplication from collapsing earlier reasoning items.
        kwargs["reasoning_item_id_policy"] = "omit"
    if config.base_url:
        provider_cls = OpenAIProvider
        if uses_deepseek:
            from townbench_agents.openai.deepseek import DeepSeekOpenAIProvider

            provider_cls = DeepSeekOpenAIProvider
        kwargs["model_provider"] = provider_cls(
            base_url=config.base_url,
            use_responses=False if uses_deepseek else None,
        )
    return RunConfig(**kwargs)


def _uses_deepseek_compatible_endpoint(config: OpenAIAgentConfig) -> bool:
    model = (config.model or "").lower()
    base_url = (config.base_url or "").lower()
    return model.startswith("deepseek-") or "deepseek.com" in base_url


def _load_runner() -> Any:
    try:
        from agents import Runner
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI Agents baseline."
        ) from exc
    return Runner


def _is_max_turns_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "MaxTurnsExceeded"


def _resolve_runner_error(env: TownBenchEnv, exc: Exception) -> str | None:
    return None if env.is_done() else str(exc)
