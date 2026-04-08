from pathlib import Path

from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def _load_phase3_env() -> TownBenchEnv:
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "phase3_town" / "scenario.yaml"
    return TownBenchEnv(load_scenario(scenario_path))


def _run_tea_loop(env: TownBenchEnv) -> None:
    env.step({"type": "call_action", "target_id": "tea_wholesaler", "args": {"action": "buy_tea_bundle"}})
    env.step({"type": "move_to", "target_id": "fuel_counter"})
    env.step({"type": "call_action", "target_id": "fuel_rack", "args": {"action": "buy_fuel_canister"}})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step({"type": "call_action", "target_id": "supply_counter", "args": {"action": "buy_packaging_sleeve"}})
    env.step({"type": "move_to", "target_id": "workshop"})
    env.step({"type": "call_action", "target_id": "tea_station", "args": {"action": "brew_tea"}})
    env.step({"type": "call_action", "target_id": "packaging_table", "args": {"action": "pack_tea"}})
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "call_action", "target_id": "goods_buyer", "args": {"action": "sell_packed_tea"}})


def _run_meal_loop(env: TownBenchEnv) -> None:
    env.step({"type": "call_action", "target_id": "ingredient_seller", "args": {"action": "buy_meal_ingredients"}})
    env.step({"type": "move_to", "target_id": "workshop"})
    env.step({"type": "call_action", "target_id": "meal_prep_table", "args": {"action": "assemble_meal_box"}})
    env.step({"type": "move_to", "target_id": "canteen"})
    env.step({"type": "call_action", "target_id": "meal_counter", "args": {"action": "sell_meal_box"}})


def _run_repair_loop_from_canteen(env: TownBenchEnv) -> None:
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step({"type": "call_action", "target_id": "supply_counter", "args": {"action": "buy_repair_part"}})
    env.step({"type": "move_to", "target_id": "workshop"})
    env.step({"type": "call_action", "target_id": "repair_bench", "args": {"action": "service_kettle"}})
    env.step({"type": "move_to", "target_id": "service_depot"})
    env.step({"type": "call_action", "target_id": "pickup_clerk", "args": {"action": "collect_service_fee"}})


def test_phase3_scenario_loads_dynamic_economic_content():
    env = _load_phase3_env()
    observation = env.reset()

    assert env.state.scenario_id == "phase3_town"
    assert observation.current_location.location_id == "plaza"
    assert observation.agent.stats == {"carry_limit": 3}
    assert set(env.state.skills) == {"tea_operations", "cashflow_recovery", "service_contracts"}
    assert len(env.state.dynamic_rules) == 4


def test_phase3_supply_counter_is_visible_but_closed_before_opening_time():
    env = _load_phase3_env()
    env.reset()
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})

    observation = env.get_observation()
    closed_purchase = env.step(
        {"type": "call_action", "target_id": "supply_counter", "args": {"action": "buy_packaging_sleeve"}}
    )

    assert observation.visible_objects[0].object_id == "supply_counter"
    assert observation.visible_objects[0].visible_state["open"] is False
    assert closed_purchase.success is False
    assert closed_purchase.warnings == ["action_temporarily_unavailable"]
    assert closed_purchase.data["visible_state"]["open"] is False


def test_phase3_dynamic_windows_reward_time_sensitive_loops():
    env = _load_phase3_env()
    env.reset()
    env.step({"type": "move_to", "target_id": "market"})

    _run_tea_loop(env)
    assert env.state.current_time == "Day 1, 09:48"
    assert env.state.agent.money == 25

    _run_meal_loop(env)
    assert env.state.current_time == "Day 1, 10:36"
    assert env.state.agent.money == 31

    _run_repair_loop_from_canteen(env)
    assert env.state.current_time == "Day 1, 11:48"
    assert env.state.agent.money == 41
    assert env.state.agent.inventory == {}
    assert env.state.agent.location_id == "service_depot"
