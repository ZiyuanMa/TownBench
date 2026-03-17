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
        "You are solving a TownBench episode. Your standing objective is to improve the agent's economic state, "
        "especially money, while respecting time and energy limits. Use the provided tools instead of inventing "
        "actions. Read tool outputs carefully, act only from the public context you are given, and prefer actions "
        "that create or preserve economic value. Do not assume the episode ends just because one task or order is "
        "finished. If the environment is still in progress, continue unless there is no clearly profitable next step. "
        "Before concluding that you are done, check the current status."
    )


def _load_agent_class() -> type:
    try:
        from agents import Agent
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI baseline."
        ) from exc
    return Agent
