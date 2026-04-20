from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def resolve_episode_env(
    *,
    scenario_path: str | Path | None,
    env: TownBenchEnv | None,
) -> TownBenchEnv:
    if env is not None:
        return env
    if scenario_path is None:
        raise ValueError("Provide either `scenario_path` or `env` when running an agent episode.")
    return TownBenchEnv(load_scenario(scenario_path))


def build_episode_initial_input(
    *,
    opening_briefing: str,
    public_rules: list[str],
    initial_observation: dict[str, Any] | str,
) -> str:
    sections = []
    if opening_briefing:
        sections.append(f"Opening briefing:\n{opening_briefing}")
    if public_rules:
        rules_block = "\n".join(f"- {rule}" for rule in public_rules)
        sections.append(f"Public rules:\n{rules_block}")
    if isinstance(initial_observation, str):
        rendered_observation = initial_observation
    else:
        rendered_observation = json.dumps(initial_observation, ensure_ascii=False, indent=2)
    sections.append(f"Initial observation:\n{rendered_observation}")
    return "\n\n".join(sections)
