from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agents.langchain.agent import build_langchain_agent
from agents.langchain.config import LangChainAgentConfig
from engine.rendering import render_initial_observation
from evaluation.results import EpisodeRunResult, build_episode_result
from runtime.env import TownBenchEnv
from runtime.episode import build_episode_initial_input, resolve_episode_env

TextDeltaHandler = Callable[[str], None]
EventHandler = Callable[[str], None]


def run_langchain_agent_episode(
    *,
    scenario_path: str | Path | None = None,
    env: TownBenchEnv | None = None,
    config: LangChainAgentConfig | None = None,
    build_agent_fn: Callable[..., Any] | None = None,
    create_agent_fn: Callable[..., Any] | None = None,
    model_factory: Callable[[LangChainAgentConfig], Any] | None = None,
    tool_factory=None,
) -> EpisodeRunResult:
    prepared = _prepare_episode_run(
        scenario_path=scenario_path,
        env=env,
        config=config,
        build_agent_fn=build_agent_fn,
        create_agent_fn=create_agent_fn,
        model_factory=model_factory,
        tool_factory=tool_factory,
    )
    outcome = _run_sync_episode(prepared)
    return build_episode_result(
        env=prepared.env,
        final_output=outcome.final_output,
        runner_error=outcome.runner_error,
    )


async def run_langchain_agent_episode_streamed(
    *,
    scenario_path: str | Path | None = None,
    env: TownBenchEnv | None = None,
    config: LangChainAgentConfig | None = None,
    build_agent_fn: Callable[..., Any] | None = None,
    create_agent_fn: Callable[..., Any] | None = None,
    model_factory: Callable[[LangChainAgentConfig], Any] | None = None,
    tool_factory=None,
    on_text_delta: TextDeltaHandler | None = None,
    on_event: EventHandler | None = None,
) -> EpisodeRunResult:
    prepared = _prepare_episode_run(
        scenario_path=scenario_path,
        env=env,
        config=config,
        build_agent_fn=build_agent_fn,
        create_agent_fn=create_agent_fn,
        model_factory=model_factory,
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
    )


class _PreparedEpisodeRun:
    def __init__(
        self,
        *,
        env: TownBenchEnv,
        config: LangChainAgentConfig,
        agent: Any,
        agent_input: dict[str, Any],
        invoke_config: dict[str, Any] | None,
    ) -> None:
        self.env = env
        self.config = config
        self.agent = agent
        self.agent_input = agent_input
        self.invoke_config = invoke_config


class _RunnerOutcome:
    def __init__(self, *, final_output: str, runner_error: str | None) -> None:
        self.final_output = final_output
        self.runner_error = runner_error


def _prepare_episode_run(
    *,
    scenario_path: str | Path | None,
    env: TownBenchEnv | None,
    config: LangChainAgentConfig | None,
    build_agent_fn: Callable[..., Any] | None,
    create_agent_fn: Callable[..., Any] | None,
    model_factory: Callable[[LangChainAgentConfig], Any] | None,
    tool_factory,
) -> _PreparedEpisodeRun:
    active_env = resolve_episode_env(scenario_path=scenario_path, env=env)
    initial_observation = active_env.reset()
    resolved_config = config or LangChainAgentConfig.from_env()
    agent_builder = build_agent_fn or build_langchain_agent
    agent = agent_builder(
        active_env,
        resolved_config,
        create_agent_fn=create_agent_fn,
        model_factory=model_factory,
        tool_factory=tool_factory,
    )
    agent_input = {
        "messages": [
            {
                "role": "user",
                "content": build_episode_initial_input(
                    opening_briefing=active_env.state.opening_briefing,
                    public_rules=active_env.state.public_rules,
                    initial_observation=render_initial_observation(initial_observation),
                ),
            }
        ]
    }
    invoke_config = (
        {"recursion_limit": resolved_config.recursion_limit}
        if resolved_config.recursion_limit is not None
        else None
    )
    return _PreparedEpisodeRun(
        env=active_env,
        config=resolved_config,
        agent=agent,
        agent_input=agent_input,
        invoke_config=invoke_config,
    )


def _run_sync_episode(prepared: _PreparedEpisodeRun) -> _RunnerOutcome:
    runner_error: str | None = None
    final_output = ""
    try:
        result = _invoke_agent(prepared.agent, prepared.agent_input, prepared.invoke_config)
        final_output = _extract_final_output(result)
    except Exception as exc:  # pragma: no cover - exercised by tests via fake exception
        if not _is_recursion_limit_error(exc):
            raise
        runner_error = _resolve_runner_error(prepared.env, exc)
    return _RunnerOutcome(final_output=final_output, runner_error=runner_error)


async def _run_streamed_episode(
    prepared: _PreparedEpisodeRun,
    *,
    on_text_delta: TextDeltaHandler | None,
    on_event: EventHandler | None,
) -> _RunnerOutcome:
    text_fragments: list[str] = []
    latest_model_text = ""
    runner_error: str | None = None
    try:
        async for chunk in _astream_agent(prepared.agent, prepared.agent_input, prepared.invoke_config):
            delta, latest_model_text = _handle_stream_chunk(
                chunk,
                on_text_delta=on_text_delta,
                on_event=on_event,
                latest_model_text=latest_model_text,
            )
            if delta:
                text_fragments.append(delta)
    except Exception as exc:  # pragma: no cover - exercised by tests via fake exception
        if not _is_recursion_limit_error(exc):
            raise
        runner_error = _resolve_runner_error(prepared.env, exc)

    return _RunnerOutcome(
        final_output="".join(text_fragments) or latest_model_text,
        runner_error=runner_error,
    )


def _invoke_agent(agent: Any, agent_input: dict[str, Any], invoke_config: dict[str, Any] | None) -> Any:
    if invoke_config is None:
        return agent.invoke(agent_input)
    return agent.invoke(agent_input, config=invoke_config)


async def _astream_agent(agent: Any, agent_input: dict[str, Any], invoke_config: dict[str, Any] | None):
    kwargs: dict[str, Any] = {
        "stream_mode": ["messages", "updates"],
        "version": "v2",
    }
    if invoke_config is not None:
        kwargs["config"] = invoke_config
    async for chunk in agent.astream(agent_input, **kwargs):
        yield chunk


def _handle_stream_chunk(
    chunk: Any,
    *,
    on_text_delta: TextDeltaHandler | None,
    on_event: EventHandler | None,
    latest_model_text: str,
) -> tuple[str, str]:
    if not isinstance(chunk, dict):
        return "", latest_model_text

    chunk_type = chunk.get("type")
    if chunk_type == "messages":
        token, _metadata = chunk.get("data", (None, None))
        delta = _extract_text_from_message(token)
        if delta and on_text_delta is not None:
            on_text_delta(delta)
        return delta, latest_model_text

    if chunk_type != "updates":
        return "", latest_model_text

    for step, data in chunk.get("data", {}).items():
        messages = data.get("messages", []) if isinstance(data, dict) else []
        if not messages:
            continue
        message = messages[-1]
        if step == "model":
            if _message_has_tool_calls(message):
                if on_event is not None:
                    on_event("tool_called")
            else:
                latest_model_text = _extract_text_from_message(message) or latest_model_text
        elif step == "tools" and on_event is not None:
            on_event(f"tool_output: {_extract_message_summary(message)}")

    return "", latest_model_text


def _extract_final_output(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            return _extract_text_from_message(messages[-1])
    final_output = getattr(result, "final_output", None)
    if isinstance(final_output, str):
        return final_output
    return str(result or "")


def _extract_message_summary(message: Any) -> str:
    text = _extract_text_from_message(message)
    if text:
        return text
    content = getattr(message, "content", None)
    if content is not None:
        return str(content)
    content_blocks = getattr(message, "content_blocks", None)
    if content_blocks is not None:
        return str(content_blocks)
    return str(message)


def _extract_text_from_message(message: Any) -> str:
    text = _extract_text_blocks(getattr(message, "content_blocks", None))
    if text:
        return text
    return _extract_text_blocks(getattr(message, "content", None))


def _extract_text_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    fragments: list[str] = []
    for block in content:
        if isinstance(block, str):
            fragments.append(block)
            continue
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            fragments.append(block["text"])
    return "".join(fragments)


def _message_has_tool_calls(message: Any) -> bool:
    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(tool_calls, list) and tool_calls:
        return True
    content_blocks = getattr(message, "content_blocks", None)
    if not isinstance(content_blocks, list):
        return False
    return any(isinstance(block, dict) and block.get("type") == "tool_call" for block in content_blocks)


def _is_recursion_limit_error(exc: Exception) -> bool:
    return (
        exc.__class__.__name__ == "GraphRecursionError"
        or getattr(exc, "lc_error_code", None) == "GRAPH_RECURSION_LIMIT"
    )


def _resolve_runner_error(env: TownBenchEnv, exc: Exception) -> str | None:
    return None if env.is_done() else str(exc)
