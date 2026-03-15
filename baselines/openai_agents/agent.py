from __future__ import annotations

from typing import Any, Callable, Optional

from baselines.openai_agents.config import OpenAIAgentsConfig
from baselines.openai_agents.tools import ToolDecorator, build_townbench_tools
from runtime.env import TownBenchEnv


def build_openai_agent(
    env: TownBenchEnv,
    config: Optional[OpenAIAgentsConfig] = None,
    *,
    agent_cls: Optional[type] = None,
    function_tool_decorator: Optional[ToolDecorator] = None,
) -> Any:
    config = config or OpenAIAgentsConfig()
    agent_type = agent_cls or _load_agent_class()
    tools = build_townbench_tools(env, function_tool_decorator=function_tool_decorator)

    kwargs: dict[str, Any] = {
        "name": config.agent_name,
        "instructions": config.system_prompt or build_default_instructions(),
        "tools": tools,
    }
    if config.model:
        kwargs["model"] = config.model
    return agent_type(**kwargs)


def build_default_instructions() -> str:
    return (
        "You are solving a TownBench episode. Use the provided tools instead of inventing actions. "
        "Read tool outputs carefully, keep notes when useful, and act only from the public context you are given."
    )


def _load_agent_class() -> type:
    try:
        from agents import Agent
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI baseline."
        ) from exc
    return Agent
