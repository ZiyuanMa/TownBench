from pathlib import Path

from engine.rendering import render_initial_observation, render_tool_result
from engine.state import (
    CallableActionArgumentSpec,
    CallableActionDefinition,
    CallableActionMatcher,
    CallableActionRoute,
    DynamicCondition,
    DynamicRule,
    DynamicRuleApplication,
    ObjectActionEffect,
    ObjectDynamicOverride,
    TimeWindow,
)
from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def _load_env(scenario_name: str) -> TownBenchEnv:
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / scenario_name / "scenario.yaml"
    return TownBenchEnv(load_scenario(scenario_path))


def test_render_initial_observation_text_preserves_public_context():
    env = _load_env("demo_town")
    observation = env.reset()

    rendered = render_initial_observation(observation)

    assert "Current time: Day 1, 08:00" in rendered
    assert "Current location: Plaza (plaza)" in rendered
    assert "Nearby locations: library, workshop" in rendered
    assert "Visible objects:" in rendered
    assert "Notice Board (notice_board): A board with public notices." in rendered


def test_render_tool_result_success_includes_snapshot():
    env = _load_env("demo_town")
    env.reset()

    result = env.step({"type": "move_to", "target_id": "workshop"})
    rendered = render_tool_result({"type": "move_to", "target_id": "workshop"}, result)

    assert "Moved to `Workshop`." in rendered
    assert "Effects: time +12, energy -3" in rendered
    assert "Current snapshot:" in rendered
    assert "Location: Workshop (workshop)" in rendered


def test_render_snapshot_shows_parameterized_callable_actions():
    env = _load_env("multi_area_town")
    env.reset()
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "move_to", "target_id": "supply_shop"})
    rendered = render_tool_result({"type": "move_to", "target_id": "supply_shop"}, result)

    assert "Supply Counter (supply_counter)" in rendered
    assert "Callable actions: buy(item_id: packaging_sleeve|repair_part)." in rendered


def test_render_tool_result_hides_internal_world_flags_for_missing_prerequisites():
    env = _load_env("demo_town")
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})

    result = env.step({"type": "call_action", "target_id": "completion_log", "action_name": "record_order"})
    rendered = render_tool_result(
        {"type": "call_action", "target_id": "completion_log", "action_name": "record_order"},
        result,
    )

    assert "Hint: This action depends on prior progress that has not been completed yet." in rendered
    assert "What to try next:" in rendered
    assert "Requested target: completion_log" in rendered
    assert "tea_ready" not in rendered
    assert "Required world flags" not in rendered


def test_render_tool_result_surfaces_exposed_actions_for_action_not_exposed():
    env = _load_env("demo_town")
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})

    result = env.step({"type": "call_action", "target_id": "tea_station", "action_name": "record_order"})
    rendered = render_tool_result(
        {"type": "call_action", "target_id": "tea_station", "action_name": "record_order"},
        result,
    )

    assert "Hint: That action is not currently exposed on the target object." in rendered
    assert "Callable actions on object: brew_tea" in rendered
    assert "Visible state now: brewed_today=False" in rendered


def test_render_tool_result_surfaces_missing_inventory_context(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["repair_device"]
    env.state.objects["counter"].action_effects = {
        "repair_device": ObjectActionEffect(
            message="Repaired device.",
            required_inventory={"repair_kit": 1},
            inventory_delta={"repair_kit": -1},
            money_delta=9,
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "repair_device"})
    rendered = render_tool_result(
        {"type": "call_action", "target_id": "counter", "action_name": "repair_device"},
        result,
    )

    assert "Hint: You do not currently have the inventory items this action requires." in rendered
    assert "Required inventory: repair_kit=1" in rendered
    assert "Current inventory: none" in rendered


def test_render_tool_result_surfaces_temporary_unavailability(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.objects["counter"].actionable = True
    state.objects["counter"].callable_actions = {
        "buy": CallableActionDefinition(
            arguments={
                "item_id": CallableActionArgumentSpec(options=["snack"]),
            },
            routes=[
                CallableActionRoute(
                    match={"item_id": "snack"},
                    effect=ObjectActionEffect(message="Bought a snack."),
                )
            ],
        )
    }
    state.dynamic_rules = [
        DynamicRule(
            rule_id="counter_closed_early",
            when=DynamicCondition(time_window=TimeWindow(start="17:00", end="08:30")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"open": False},
                        disabled_callable_actions=[CallableActionMatcher(action_name="buy")],
                    )
                }
            ),
        )
    ]
    env = TownBenchEnv(state)
    env.reset()

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "action_name": "buy",
            "args": {"item_id": "snack"},
        }
    )
    rendered = render_tool_result(
        {
            "type": "call_action",
            "target_id": "counter",
            "action_name": "buy",
            "args": {"item_id": "snack"},
        },
        result,
    )

    assert "Hint: That action exists on the target, but it is temporarily unavailable right now." in rendered
    assert "Check the current time and the object's visible state before retrying." in rendered
    assert "Current time:" in rendered
    assert "Visible state now: open=False" in rendered
