from __future__ import annotations

from typing import Any, Callable

from townbench_agents.common import build_default_instructions
from townbench_agents.langchain.config import LangChainAgentConfig
from townbench_agents.langchain.tools import build_townbench_tools
from runtime.env import TownBenchEnv


def build_langchain_agent(
    env: TownBenchEnv,
    config: LangChainAgentConfig | None = None,
    *,
    create_agent_fn: Callable[..., Any] | None = None,
    model_factory: Callable[[LangChainAgentConfig], Any] | None = None,
    tool_factory=None,
) -> Any:
    resolved_config = config or LangChainAgentConfig.from_env()
    model_builder = model_factory or _build_chat_model
    agent_factory = create_agent_fn or _load_create_agent()
    tools = build_townbench_tools(env, tool_factory=tool_factory)

    return agent_factory(
        model_builder(resolved_config),
        tools,
        system_prompt=resolved_config.system_prompt or build_default_instructions(env),
    )


def _build_chat_model(config: LangChainAgentConfig) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain-openai is not installed. Install dependencies before using the LangChain agent."
        ) from exc

    if not config.model:
        raise RuntimeError("LANGCHAIN_AGENT_MODEL is required. Fill it in `.env` or pass it explicitly.")

    kwargs: dict[str, Any] = {"model": config.model}
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens
    if config.timeout is not None:
        kwargs["timeout"] = config.timeout
    if config.max_retries is not None:
        kwargs["max_retries"] = config.max_retries
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return ChatOpenAI(**kwargs)


def _load_create_agent() -> Callable[..., Any]:
    try:
        from langchain.agents import create_agent
    except ImportError as exc:
        raise RuntimeError(
            "langchain is not installed. Install dependencies before using the LangChain agent."
        ) from exc
    return create_agent
