from pathlib import Path

import pytest

from evaluation.results import EpisodeRunResult, build_episode_result
from runtime.env import TownBenchEnv
from runtime.episode import build_episode_initial_input, resolve_episode_env
from scenario.loader import load_scenario


def test_build_episode_initial_input_renders_sections():
    rendered = build_episode_initial_input(
        opening_briefing="Welcome to town.",
        public_rules=["Rule one", "Rule two"],
        initial_observation={"location": "plaza"},
    )

    assert "Opening briefing:\nWelcome to town." in rendered
    assert "Public rules:\n- Rule one\n- Rule two" in rendered
    assert '"location": "plaza"' in rendered


def test_resolve_episode_env_uses_explicit_env():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))

    assert resolve_episode_env(scenario_path=None, env=env) is env


def test_resolve_episode_env_requires_input():
    with pytest.raises(ValueError, match="Provide either `scenario_path` or `env`"):
        resolve_episode_env(scenario_path=None, env=None)


def test_build_episode_result_scores_final_state():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})

    result = build_episode_result(
        env=env,
        final_output="Moved once.",
        runner_error=None,
    )

    assert isinstance(result, EpisodeRunResult)
    assert result.final_output == "Moved once."
    assert result.score.step_count == 1
    assert result.trace[0].normalized_action["type"] == "move_to"
