from pathlib import Path

import pytest
from pydantic import ValidationError

from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def test_load_scenario_builds_world_state():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"

    state = load_scenario(scenario_path)

    assert state.scenario_id == "demo_town"
    assert state.agent.location_id == "plaza"
    assert state.areas == {}
    assert set(state.locations) == {"plaza", "library", "workshop"}
    assert state.locations["plaza"].area_id is None
    assert set(state.objects) == {
        "notice_board",
        "recipe_card",
        "archive_book",
        "tea_station",
        "storage_shelf",
        "completion_log",
    }
    assert state.objects["notice_board"].resource_content.startswith("Shift tea work")
    assert state.objects["recipe_card"].resource_content.startswith("Workshop recipe reminder")
    assert state.skills["tea_basics"].name == "Tea Basics"
    assert state.skills["tea_basics"].description.startswith("Basic workshop tea preparation steps")
    assert set(state.skills) == {"tea_basics", "inventory_rules", "order_fulfillment", "tea_history"}
    assert state.skills["tea_basics"].content.startswith("# Tea Basics")
    assert state.opening_briefing.startswith("You arrived in town")
    assert state.public_rules[0].startswith("Actions cost time")
    assert state.action_costs["move_to"].time_delta == 12
    assert [rule.event_id for rule in state.event_rules] == ["tea_ready_notice", "order_paid_notice"]
    assert state.termination_config.max_steps == 10
    assert state.termination_config.success_world_flags == []
    assert state.dynamic_rules == []


def test_load_phase3_scenario_builds_dynamic_rules():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "phase3_town" / "scenario.yaml"

    state = load_scenario(scenario_path)

    assert state.scenario_id == "phase3_town"
    assert [rule.rule_id for rule in state.dynamic_rules] == [
        "supply_counter_closed_early",
        "goods_buyer_morning_surge",
        "meal_counter_lunch_rush",
        "pickup_clerk_closed",
    ]


def test_search_is_rejected_and_open_resource_still_works():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()

    search_result = env.step({"type": "search", "args": {"query": "tea"}})
    open_result = env.step({"type": "open_resource", "target_id": "notice_board"})

    assert search_result.success is False
    assert open_result.success is True
    assert "Payment: 9 coins each time" in open_result.data["content"]


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
    assert "Basic workshop tea preparation steps" in skill_result.data["description"]
    assert action_result.success is True
    assert env.state.objects["tea_station"].visible_state["brewed_today"] is True
    assert env.state.world_flags["tea_ready"] is True
    assert env.state.agent.money == 12
    assert action_result.done is False
    assert action_result.triggered_events == ["tea_ready_notice"]
    assert env.state.objects["notice_board"].visible_state["latest_notice"] == "Fresh tea ready for pickup at the workshop"


def test_completion_log_requires_brewing_and_pays_agent():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})

    early_result = env.step(
        {
            "type": "call_action",
            "target_id": "completion_log",
            "args": {"action": "record_order"},
        }
    )
    brew_result = env.step(
        {
            "type": "call_action",
            "target_id": "tea_station",
            "args": {"action": "brew_tea"},
        }
    )
    paid_result = env.step(
        {
            "type": "call_action",
            "target_id": "completion_log",
            "args": {"action": "record_order"},
        }
    )

    assert early_result.success is False
    assert early_result.warnings == ["missing_prerequisites"]
    assert brew_result.success is True
    assert paid_result.success is True
    assert paid_result.money_delta == 9
    assert env.state.agent.money == 21
    assert paid_result.data["world_flags"]["order_logged"] is False
    assert paid_result.data["world_flags"]["tea_ready"] is False
    assert paid_result.data["world_flags"]["payment_posted"] is True
    assert paid_result.data["visible_state"]["last_entry"] == "payout_collected"
    assert env.state.world_flags["order_logged"] is False
    assert env.state.world_flags["tea_ready"] is False
    assert env.state.world_flags["payment_posted"] is True
    assert paid_result.triggered_events == ["order_paid_notice"]
    assert env.state.objects["notice_board"].visible_state["latest_notice"] == "Tea order paid. Another shift order is now posted."
    assert env.state.objects["completion_log"].visible_state["last_entry"] == "payout_collected"


def test_paid_order_reopens_the_loop_for_another_payout():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})

    first_brew = env.step({"type": "call_action", "target_id": "tea_station", "args": {"action": "brew_tea"}})
    first_pay = env.step(
        {"type": "call_action", "target_id": "completion_log", "args": {"action": "record_order"}}
    )
    second_brew = env.step({"type": "call_action", "target_id": "tea_station", "args": {"action": "brew_tea"}})
    second_pay = env.step(
        {"type": "call_action", "target_id": "completion_log", "args": {"action": "record_order"}}
    )

    assert first_brew.triggered_events == ["tea_ready_notice"]
    assert first_pay.triggered_events == ["order_paid_notice"]
    assert second_brew.triggered_events == ["tea_ready_notice"]
    assert second_pay.triggered_events == ["order_paid_notice"]
    assert env.state.agent.money == 30
    assert env.state.objects["notice_board"].visible_state["latest_notice"] == "Tea order paid. Another shift order is now posted."


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


def test_loader_rejects_dynamic_rule_overriding_unknown_object_action(tmp_path):
    scenario_file = tmp_path / "bad_dynamic_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken_dynamic
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects:
  - object_id: stall
    name: Stall
    object_type: stall
    location_id: plaza
    summary: A simple stall.
    actionable: true
    action_ids: [buy_item]
    action_effects:
      buy_item:
        message: Bought one item.
        required_money: 1
        money_delta: -1
dynamic_rules:
  - rule_id: bad_override
    when:
      time_window:
        start: "08:00"
        end: "09:00"
    apply:
      object_overrides:
        stall:
          action_overrides:
            sell_item:
              money_delta: 2
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="overrides unknown action"):
        load_scenario(scenario_file)


def test_loader_rejects_dynamic_rule_enabling_unknown_object_action(tmp_path):
    scenario_file = tmp_path / "bad_dynamic_enabled_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken_dynamic
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects:
  - object_id: stall
    name: Stall
    object_type: stall
    location_id: plaza
    summary: A simple stall.
    actionable: true
    action_ids: [buy_item]
    action_effects:
      buy_item:
        message: Bought one item.
        required_money: 1
        money_delta: -1
dynamic_rules:
  - rule_id: bad_enable
    when:
      time_window:
        start: "08:00"
        end: "09:00"
    apply:
      object_overrides:
        stall:
          enabled_actions: [sell_item]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="enables unknown action"):
        load_scenario(scenario_file)


def test_loader_parses_areas_and_location_area_ids(tmp_path):
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: area_demo
initial_agent_state:
  location_id: lobby
areas:
  - area_id: library
    name: Library
    description: A quiet public library.
locations:
  - location_id: lobby
    name: Lobby
    description: The library entrance.
    area_id: library
  - location_id: archive
    name: Archive
    description: A records room.
    area_id: library
objects: []
skills: []
""".strip(),
        encoding="utf-8",
    )

    state = load_scenario(scenario_file)

    assert set(state.areas) == {"library"}
    assert state.areas["library"].name == "Library"
    assert state.locations["lobby"].area_id == "library"
    assert state.locations["archive"].area_id == "library"


def test_loader_rejects_duplicate_area_ids(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: lobby
areas:
  - area_id: library
    name: Library
  - area_id: library
    name: Duplicate Library
locations:
  - location_id: lobby
    name: Lobby
    description: The entry room.
    area_id: library
objects: []
skills: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate area id"):
        load_scenario(scenario_file)


def test_loader_rejects_unknown_location_area_reference(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: lobby
locations:
  - location_id: lobby
    name: Lobby
    description: The entry room.
    area_id: library
objects: []
skills: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="references unknown area"):
        load_scenario(scenario_file)


def test_loader_rejects_authored_location_object_ids_even_with_area_id_present(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: lobby
areas:
  - area_id: library
    name: Library
locations:
  - location_id: lobby
    name: Lobby
    description: The entry room.
    area_id: library
    object_ids: [notice_board]
objects:
  - object_id: notice_board
    name: Notice Board
    object_type: board
    location_id: lobby
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


def test_loader_rejects_unknown_initial_agent_fields(tmp_path):
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: plaza
  bonus_moves: 2
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects: []
skills: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_scenario(scenario_file)


def test_loader_rejects_unknown_action_cost_fields(tmp_path):
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
action_costs:
  move_to:
    time_delta: 1
    bonus_moves: 2
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_scenario(scenario_file)


def test_loader_rejects_unknown_action_effect_fields(tmp_path):
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
  - object_id: tea_station
    name: Tea Station
    object_type: station
    location_id: plaza
    summary: A station.
    action_ids: [brew_tea]
    action_effects:
      brew_tea:
        message: Brewed.
        reward_points: 3
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_scenario(scenario_file)


def test_loader_rejects_unknown_event_rule_fields(tmp_path):
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
event_rules:
  - event_id: tea_ready_notice
    trigger_once: true
    cooldown: 1
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_scenario(scenario_file)


def test_loader_rejects_unknown_termination_config_fields(tmp_path):
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
termination_config:
  max_steps: 10
  grace_turns: 2
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_scenario(scenario_file)


def test_loader_rejects_conflicting_resource_sources(tmp_path):
    resource_file = tmp_path / "notice.txt"
    resource_file.write_text("File notice.", encoding="utf-8")
    scenario_file = tmp_path / "bad_scenario.yaml"
    scenario_file.write_text(
        f"""
scenario_id: broken
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects:
  - object_id: notice_board
    name: Notice Board
    object_type: board
    location_id: plaza
    summary: A board.
    readable: true
    resource_content: Inline text.
    resource_file: {resource_file.name}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="must define only one of `resource_content` or `resource_file`"):
        load_scenario(scenario_file)


def test_loader_preserves_inline_resource_content(tmp_path):
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: inline_resource
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects:
  - object_id: notice_board
    name: Notice Board
    object_type: board
    location_id: plaza
    summary: A board.
    readable: true
    resource_content: Inline notice text.
""".strip(),
        encoding="utf-8",
    )

    state = load_scenario(scenario_file)

    assert state.objects["notice_board"].resource_content == "Inline notice text."


def test_loader_deep_copies_nested_visible_state(tmp_path):
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: nested_visible_state
initial_agent_state:
  location_id: plaza
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects:
  - object_id: board_a
    name: Board A
    object_type: board
    location_id: plaza
    summary: First board.
    visible_state:
      nested: &shared_state
        counters:
          tea: 1
        notes:
          - ready
  - object_id: board_b
    name: Board B
    object_type: board
    location_id: plaza
    summary: Second board.
    visible_state:
      nested: *shared_state
""".strip(),
        encoding="utf-8",
    )

    state = load_scenario(scenario_file)

    first_nested = state.objects["board_a"].visible_state["nested"]
    second_nested = state.objects["board_b"].visible_state["nested"]

    assert first_nested is not second_nested
    assert first_nested["counters"] is not second_nested["counters"]
    assert first_nested["notes"] is not second_nested["notes"]

    first_nested["counters"]["tea"] = 9
    first_nested["notes"].append("updated")

    assert second_nested["counters"]["tea"] == 1
    assert second_nested["notes"] == ["ready"]


def test_loader_parses_agent_stat_fields_on_object_actions(tmp_path):
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: stats_action_effects
initial_agent_state:
  location_id: plaza
  stats:
    carry_limit: 2
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects:
  - object_id: locker_desk
    name: Locker Desk
    object_type: desk
    location_id: plaza
    summary: A storage service counter.
    action_ids: [upgrade_locker]
    actionable: true
    action_effects:
      upgrade_locker:
        message: Locker upgraded.
        required_agent_stats:
          carry_limit: 2
        agent_stat_deltas:
          carry_limit: 3
        set_world_flags:
          locker_upgraded: true
""".strip(),
        encoding="utf-8",
    )

    state = load_scenario(scenario_file)
    effect = state.objects["locker_desk"].action_effects["upgrade_locker"]

    assert state.agent.stats == {"carry_limit": 2}
    assert effect.required_agent_stats == {"carry_limit": 2}
    assert effect.agent_stat_deltas == {"carry_limit": 3}
    assert effect.set_world_flags == {"locker_upgraded": True}


def test_phase2_loader_authors_locker_upgrade_as_one_time_gated_capacity_increase():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "phase2_town" / "scenario.yaml"

    state = load_scenario(scenario_path)
    effect = state.objects["locker_desk"].action_effects["buy_locker_upgrade"]

    assert state.agent.stats == {"carry_limit": 3}
    assert state.world_flags["locker_upgrade_purchased"] is False
    assert effect.required_world_flags == {"locker_upgrade_purchased": False}
    assert effect.agent_stat_deltas == {"carry_limit": 2}
    assert effect.set_world_flags == {"locker_upgrade_purchased": True}


def test_loader_rejects_initial_agent_inventory_that_exceeds_carry_limit(tmp_path):
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: broken
initial_agent_state:
  location_id: plaza
  inventory:
    apple: 2
  stats:
    carry_limit: 1
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exceeds the configured carry_limit"):
        load_scenario(scenario_file)


def test_loader_accepts_non_empty_initial_inventory_within_carry_limit(tmp_path):
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
scenario_id: valid
initial_agent_state:
  location_id: plaza
  inventory:
    apple: 2
  stats:
    carry_limit: 3
locations:
  - location_id: plaza
    name: Plaza
    description: A plaza.
objects: []
""".strip(),
        encoding="utf-8",
    )

    state = load_scenario(scenario_file)

    assert state.agent.inventory == {"apple": 2}
    assert state.agent.stats == {"carry_limit": 3}


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


def test_loader_rejects_action_effects_with_unknown_move_target(tmp_path):
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
  - object_id: cart
    name: Cart
    object_type: cart
    location_id: plaza
    summary: A paid cart.
    action_ids: [ride]
    actionable: true
    action_effects:
      ride:
        message: Ride.
        move_to_location_id: workshop
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="references unknown location"):
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
