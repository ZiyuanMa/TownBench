from pathlib import Path

from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def _load_phase2_env() -> TownBenchEnv:
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "phase2_town" / "scenario.yaml"
    return TownBenchEnv(load_scenario(scenario_path))


def _run_tea_loop(env: TownBenchEnv) -> None:
    env.step({"type": "call_action", "target_id": "tea_wholesaler", "action_name": "buy_tea_bundle"})
    env.step({"type": "move_to", "target_id": "fuel_counter"})
    env.step({"type": "call_action", "target_id": "fuel_rack", "action_name": "buy_fuel_canister"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step({"type": "call_action", "target_id": "supply_counter", "action_name": "buy_packaging_sleeve"})
    env.step({"type": "move_to", "target_id": "workshop"})
    env.step({"type": "call_action", "target_id": "tea_station", "action_name": "brew_tea"})
    env.step({"type": "call_action", "target_id": "packaging_table", "action_name": "pack_tea"})
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "call_action", "target_id": "goods_buyer", "action_name": "sell_packed_tea"})


def _run_meal_loop(env: TownBenchEnv) -> None:
    env.step({"type": "call_action", "target_id": "ingredient_seller", "action_name": "buy_meal_ingredients"})
    env.step({"type": "move_to", "target_id": "workshop"})
    env.step({"type": "call_action", "target_id": "meal_prep_table", "action_name": "assemble_meal_box"})
    env.step({"type": "move_to", "target_id": "canteen"})
    env.step({"type": "call_action", "target_id": "meal_counter", "action_name": "sell_meal_box"})


def _run_repair_loop_from_canteen(env: TownBenchEnv) -> None:
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step({"type": "call_action", "target_id": "supply_counter", "action_name": "buy_repair_part"})
    env.step({"type": "move_to", "target_id": "workshop"})
    env.step({"type": "call_action", "target_id": "repair_bench", "action_name": "service_kettle"})
    env.step({"type": "move_to", "target_id": "service_depot"})
    env.step({"type": "call_action", "target_id": "pickup_clerk", "action_name": "collect_service_fee"})


def test_phase2_scenario_loads_expected_economic_content():
    env = _load_phase2_env()
    observation = env.reset()

    assert env.state.scenario_id == "phase2_town"
    assert observation.current_location.location_id == "plaza"
    assert observation.agent.stats == {"carry_limit": 3}
    assert set(env.state.locations) == {
        "plaza",
        "market",
        "workshop",
        "canteen",
        "supply_shop",
        "storage_room",
        "service_depot",
        "fuel_counter",
    }
    assert set(env.state.skills) == {"tea_operations", "cashflow_recovery", "service_contracts"}
    assert env.state.objects["operations_board"].resource_content.startswith("Production district operating summary")
    assert env.state.objects["usage_notice"].resource_content.startswith("Fuel usage notice")
    assert env.state.objects["tea_batch_crate"].visible_state["batch_load"] == 5
    assert env.state.objects["locker_desk"].visible_state["upgrade_status"] == "available"


def test_phase2_tea_loop_can_repeat_profitably():
    env = _load_phase2_env()
    env.reset()
    env.step({"type": "move_to", "target_id": "market"})

    _run_tea_loop(env)
    _run_tea_loop(env)

    assert env.state.agent.money == 28
    assert env.state.agent.inventory == {}
    assert env.state.agent.location_id == "market"


def test_phase2_meal_loop_is_low_capital_fallback():
    env = _load_phase2_env()
    env.reset()
    env.state.agent.money = 2
    env.step({"type": "move_to", "target_id": "market"})

    _run_meal_loop(env)

    assert env.state.agent.money == 5
    assert env.state.agent.inventory == {}
    assert env.state.agent.location_id == "canteen"


def test_phase2_repair_loop_requires_more_startup_capital_than_meal_loop():
    env = _load_phase2_env()
    env.reset()
    env.state.agent.money = 5
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})

    early_repair = env.step(
        {"type": "call_action", "target_id": "supply_counter", "action_name": "buy_repair_part"}
    )
    env.step({"type": "move_to", "target_id": "market"})
    _run_meal_loop(env)
    _run_repair_loop_from_canteen(env)

    assert early_repair.success is False
    assert early_repair.warnings == ["insufficient_money"]
    assert env.state.agent.money == 18
    assert env.state.agent.inventory == {}
    assert env.state.agent.location_id == "service_depot"


def test_phase2_locker_upgrade_enables_bulk_input_purchase_and_is_one_time():
    env = _load_phase2_env()
    env.reset()
    env.state.agent.money = 20
    env.step({"type": "move_to", "target_id": "market"})

    early_bulk = env.step({"type": "call_action", "target_id": "tea_batch_crate", "action_name": "buy_tea_batch"})

    env.step({"type": "move_to", "target_id": "plaza"})
    env.step({"type": "move_to", "target_id": "storage_room"})
    upgrade = env.step(
        {"type": "call_action", "target_id": "locker_desk", "action_name": "buy_locker_upgrade"}
    )
    second_upgrade = env.step(
        {"type": "call_action", "target_id": "locker_desk", "action_name": "buy_locker_upgrade"}
    )
    env.step({"type": "move_to", "target_id": "plaza"})
    env.step({"type": "move_to", "target_id": "market"})
    late_bulk = env.step({"type": "call_action", "target_id": "tea_batch_crate", "action_name": "buy_tea_batch"})

    assert early_bulk.success is False
    assert early_bulk.warnings == ["inventory_capacity_exceeded"]
    assert upgrade.success is True
    assert upgrade.data["stats"] == {"carry_limit": 5}
    assert second_upgrade.success is False
    assert second_upgrade.warnings == ["missing_prerequisites"]
    assert late_bulk.success is True
    assert env.state.agent.stats == {"carry_limit": 5}
    assert env.state.agent.inventory == {
        "tea_bundle": 2,
        "packaging_sleeve": 2,
        "fuel_canister": 1,
    }


def test_phase2_bad_inventory_can_be_cleared_to_restore_progress():
    env = _load_phase2_env()
    env.reset()
    env.step({"type": "move_to", "target_id": "market"})

    env.step({"type": "call_action", "target_id": "bargain_bin", "action_name": "buy_dusty_trinket"})
    env.step({"type": "call_action", "target_id": "bargain_bin", "action_name": "buy_dusty_trinket"})
    env.step({"type": "call_action", "target_id": "bargain_bin", "action_name": "buy_dusty_trinket"})
    blocked_buy = env.step(
        {"type": "call_action", "target_id": "ingredient_seller", "action_name": "buy_meal_ingredients"}
    )
    recovery = env.step(
        {"type": "call_action", "target_id": "goods_buyer", "action_name": "sell_dusty_trinket"}
    )
    recovered_buy = env.step(
        {"type": "call_action", "target_id": "ingredient_seller", "action_name": "buy_meal_ingredients"}
    )

    assert blocked_buy.success is False
    assert blocked_buy.warnings == ["inventory_capacity_exceeded"]
    assert recovery.success is True
    assert recovered_buy.success is True
    assert env.state.agent.inventory == {"dusty_trinket": 2, "meal_ingredients": 1}
