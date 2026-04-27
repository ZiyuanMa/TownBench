from __future__ import annotations

from typing import Any, Callable

from runtime.env import TownBenchEnv
from townbench_agents.common import build_default_instructions
from townbench_agents.openai.config import OpenAIAgentConfig
from townbench_agents.openai.tools import build_townbench_tools


def build_openai_agent(
    env: TownBenchEnv,
    config: OpenAIAgentConfig | None = None,
    *,
    agent_factory: Callable[..., Any] | None = None,
    model_settings_factory: Callable[..., Any] | None = None,
    tool_factory=None,
) -> Any:
    resolved_config = config or OpenAIAgentConfig.from_env()
    if not resolved_config.model:
        raise RuntimeError("OPENAI_AGENT_MODEL is required. Fill it in `.env` or pass it explicitly.")

    factory = agent_factory or _load_agent_factory()
    settings_factory = model_settings_factory or _load_model_settings_factory()
    tools = build_townbench_tools(env, tool_factory=tool_factory)

    return factory(
        name="TownBench Agent",
        instructions=resolved_config.system_prompt or build_default_instructions(env),
        tools=tools,
        model=resolved_config.model,
        model_settings=settings_factory(
            temperature=resolved_config.temperature,
            max_tokens=resolved_config.max_tokens,
            parallel_tool_calls=False,
        ),
    )


def _load_agent_factory() -> Callable[..., Any]:
    try:
        from agents import Agent
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI Agents baseline."
        ) from exc
    return Agent


def _load_model_settings_factory() -> Callable[..., Any]:
    try:
        from agents import ModelSettings
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI Agents baseline."
        ) from exc
    return ModelSettings
