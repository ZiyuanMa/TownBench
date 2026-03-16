from pathlib import Path

import pytest

from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def test_load_scenario_builds_world_state():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"

    state = load_scenario(scenario_path)

    assert state.scenario_id == "demo_town"
    assert state.agent.location_id == "plaza"
    assert set(state.locations) == {"plaza", "library", "workshop"}
    assert state.objects["notice_board"].resource_content.startswith("Tea order")
    assert state.skills["tea_basics"].name == "Tea Basics"
    assert state.skills["tea_basics"].description.startswith("Basic tea preparation steps")
    assert state.skills["tea_basics"].content.startswith("# Tea Basics")
    assert state.opening_briefing.startswith("You arrived in town")
    assert state.public_rules[0].startswith("Actions cost time")
    assert state.action_costs["move_to"].time_delta == 12
    assert state.event_rules[0].event_id == "tea_ready_notice"
    assert state.termination_config.max_steps == 8


def test_search_is_disabled_and_open_resource_still_works():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()

    search_result = env.step({"type": "search", "args": {"query": "tea"}})
    open_result = env.step({"type": "open_resource", "target_id": "notice_board"})

    assert search_result.success is False
    assert search_result.warnings == ["disabled_action"]
    assert open_result.success is True
    assert "fresh pot" in open_result.data["content"]


def test_load_skill_and_call_action_change_world_state():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()

    skill_result = env.step({"type": "load_skill", "target_id": "tea_basics"})
    env.step({"type": "move_to", "target_id": "workshop"})
    action_result = env.step(
        {
            "type": "call_action",
            "target_id": "tea_station",
            "args": {"action": "brew_tea"},
        }
    )

    assert skill_result.success is True
    assert skill_result.data["name"] == "Tea Basics"
    assert "Basic tea preparation steps" in skill_result.data["description"]
    assert action_result.success is True
    assert env.state.objects["tea_station"].visible_state["brewed_today"] is True
    assert env.state.world_flags["tea_ready"] is True
    assert action_result.triggered_events == ["tea_ready_notice"]
    assert env.state.objects["notice_board"].visible_state["latest_notice"] == "Fresh tea ready in the workshop"


def test_call_action_rejects_unexposed_actions():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    state = load_scenario(scenario_path)
    state.objects["tea_station"].action_ids = []
    env = TownBenchEnv(state)
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})

    action_result = env.step(
        {
            "type": "call_action",
            "target_id": "tea_station",
            "args": {"action": "brew_tea"},
        }
    )

    assert action_result.success is False
    assert action_result.warnings == ["action_not_exposed"]


def test_loader_rejects_invalid_initial_location(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: nowhere
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Initial agent location"):
        load_scenario(scenario_file)


def test_loader_rejects_duplicate_location_ids(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
  - location_id: plaza
    name: Duplicate Plaza
    description: Another plaza.
objects: []
skills: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate location id"):
        load_scenario(scenario_file)


def test_loader_rejects_unknown_location_links(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
    links: [market]
objects: []
skills: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="links to unknown location"):
        load_scenario(scenario_file)


def test_loader_rejects_authored_location_object_ids(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
    object_ids: [notice_board]
objects:
  - object_id: notice_board
    name: Notice Board
    object_type: board
    location_id: plaza
    summary: A board.
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not declare `object_ids`"):
        load_scenario(scenario_file)


def test_loader_rejects_hidden_action_effects(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects:
  - object_id: station
    name: Station
    object_type: station
    location_id: plaza
    summary: A station.
    action_ids: []
    actionable: true
    action_effects:
      hidden_action:
        message: Hidden.
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="action_effects that are not exposed"):
        load_scenario(scenario_file)


def test_loader_rejects_event_rules_with_unknown_objects(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects: []
event_rules:
  - event_id: bad_event
    set_object_visible_state:
      ghost_board:
        online: true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="references unknown object"):
        load_scenario(scenario_file)


def test_loader_rejects_skill_without_frontmatter(tmp_path):
    skill_file = tmp_path / "skill.md"
    scenario_file = tmp_path / "scenario.yaml"
    skill_file.write_text("# Missing metadata", encoding="utf-8")
    scenario_file.write_text(
        f"""
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
skills:
  - skill_id: missing_metadata
    file: {skill_file.name}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must begin with YAML frontmatter"):
        load_scenario(scenario_file)


def test_loader_rejects_skill_without_description(tmp_path):
    skill_file = tmp_path / "skill.md"
    scenario_file = tmp_path / "scenario.yaml"
    skill_file.write_text(
        """
---
name: Missing Description
---

# Missing Description
""".strip(),
        encoding="utf-8",
    )
    scenario_file.write_text(
        f"""
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
skills:
  - skill_id: missing_description
    file: {skill_file.name}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must define `description` as a non-empty string"):
        load_scenario(scenario_file)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("name", "null"),
        ("name", "false"),
        ("description", "0"),
    ],
)
def test_loader_rejects_non_string_skill_metadata(tmp_path, field_name, field_value):
    skill_file = tmp_path / "skill.md"
    scenario_file = tmp_path / "scenario.yaml"
    skill_file.write_text(
        f"""
---
name: Valid Name
description: Valid description.
{field_name}: {field_value}
---

# Invalid Skill
""".strip(),
        encoding="utf-8",
    )
    scenario_file.write_text(
        f"""
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
skills:
  - skill_id: invalid_metadata
    file: {skill_file.name}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=rf"must define `{field_name}` as a non-empty string"):
        load_scenario(scenario_file)
