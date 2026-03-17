from __future__ import annotations

import os

from typing import Literal, Optional

from pydantic import BaseModel


class OpenAIAgentsConfig(BaseModel):
    agent_name: str = "TownBench Baseline"
    model: Optional[str] = None
    max_turns: Optional[int] = None
    system_prompt: Optional[str] = None
    api: Literal["chat_completions", "responses"] = "chat_completions"
    tracing_disabled: bool = True

    @classmethod
    def from_env(cls) -> "OpenAIAgentsConfig":
        model = os.getenv("OPENAI_AGENT_MODEL") or None
        agent_name = os.getenv("OPENAI_AGENT_NAME") or "TownBench Baseline"
        system_prompt = os.getenv("OPENAI_AGENT_SYSTEM_PROMPT") or None
        api = os.getenv("OPENAI_AGENT_API", "chat_completions")
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
        )
