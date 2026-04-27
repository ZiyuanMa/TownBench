from __future__ import annotations

import os

from pydantic import BaseModel


class OpenAIAgentConfig(BaseModel):
    model: str | None = None
    max_turns: int | None = 25
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tracing_disabled: bool = False
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> "OpenAIAgentConfig":
        max_turns = _get_env_int("OPENAI_AGENT_MAX_TURNS")
        return cls(
            model=os.getenv("OPENAI_AGENT_MODEL") or None,
            max_turns=max_turns if max_turns is not None else 25,
            system_prompt=os.getenv("OPENAI_AGENT_SYSTEM_PROMPT") or None,
            temperature=_get_env_float("OPENAI_AGENT_TEMPERATURE"),
            max_tokens=_get_env_int("OPENAI_AGENT_MAX_TOKENS"),
            tracing_disabled=_get_env_bool("OPENAI_AGENT_TRACING_DISABLED", default=False),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )


def _get_env_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return float(value)


def _get_env_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return int(value)


def _get_env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}
