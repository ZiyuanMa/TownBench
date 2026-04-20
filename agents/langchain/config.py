from __future__ import annotations

import os

from pydantic import BaseModel


class LangChainAgentConfig(BaseModel):
    model: str | None = None
    recursion_limit: int | None = 25
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float | None = None
    max_retries: int | None = None
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> "LangChainAgentConfig":
        recursion_limit = _get_env_int("LANGCHAIN_AGENT_RECURSION_LIMIT")
        return cls(
            model=os.getenv("LANGCHAIN_AGENT_MODEL") or None,
            recursion_limit=recursion_limit if recursion_limit is not None else 25,
            system_prompt=os.getenv("LANGCHAIN_AGENT_SYSTEM_PROMPT") or None,
            temperature=_get_env_float("LANGCHAIN_AGENT_TEMPERATURE"),
            max_tokens=_get_env_int("LANGCHAIN_AGENT_MAX_TOKENS"),
            timeout=_get_env_float("LANGCHAIN_AGENT_TIMEOUT"),
            max_retries=_get_env_int("LANGCHAIN_AGENT_MAX_RETRIES"),
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
