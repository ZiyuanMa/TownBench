from __future__ import annotations

import os
from typing import Literal
from pydantic import BaseModel


class OpenAIAgentsConfig(BaseModel):
    agent_name: str = "TownBench Baseline"
    model: str | None = None
    max_turns: int | None = None
    system_prompt: str | None = None
    api: Literal["chat_completions", "responses"] = "chat_completions"
    tracing_disabled: bool = True
    tool_output_format: Literal["text", "json"] = "text"

    @classmethod
    def from_env(cls) -> "OpenAIAgentsConfig":
        model = os.getenv("OPENAI_AGENT_MODEL") or None
        agent_name = os.getenv("OPENAI_AGENT_NAME") or "TownBench Baseline"
        system_prompt = os.getenv("OPENAI_AGENT_SYSTEM_PROMPT") or None
        api = os.getenv("OPENAI_AGENT_API", "chat_completions")
        tool_output_format = os.getenv("OPENAI_AGENT_TOOL_OUTPUT_FORMAT", "text")
        tracing_disabled = os.getenv("OPENAI_AGENT_DISABLE_TRACING", "true").lower() not in {
            "0",
            "false",
            "no",
        }
        return cls(
            agent_name=agent_name,
            model=model,
            system_prompt=system_prompt,
            api=api,
            tracing_disabled=tracing_disabled,
            tool_output_format=tool_output_format,
        )
