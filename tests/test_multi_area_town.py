from pathlib import Path

from engine.rules import parse_time_label
from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def _load_multi_area_env() -> TownBenchEnv:
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "multi_area_town" / "scenario.yaml"
    return TownBenchEnv(load_scenario(scenario_path))


def _run_tea_loop(env: TownBenchEnv) -> None:
    env.step({"type": "call_action", "target_id": "tea_wholesaler", "action_name": "buy_tea_bundle"})
    env.step({"type": "move_to", "target_id": "fuel_counter"})
    env.step({"type": "call_action", "target_id": "fuel_rack", "action_name": "buy_fuel_canister"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step(
        {
            "type": "call_action",
            "target_id": "supply_counter",
            "action_name": "buy",
            "args": {"item_id": "packaging_sleeve"},
        }
    )
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "workshop_lobby"})
    env.step({"type": "move_to", "target_id": "tea_room"})
    env.step({"type": "call_action", "target_id": "tea_station", "action_name": "brew_tea"})
    env.step({"type": "move_to", "target_id": "packing_room"})
    env.step({"type": "call_action", "target_id": "packaging_table", "action_name": "pack_tea"})
    env.step({"type": "move_to", "target_id": "workshop_lobby"})
    env.step({"type": "move_to", "target_id": "market"})
    env.step(
        {
            "type": "call_action",
            "target_id": "goods_buyer",
            "action_name": "sell",
            "args": {"item_id": "packed_tea"},
        }
    )


def _run_meal_loop(env: TownBenchEnv) -> None:
    env.step({"type": "call_action", "target_id": "ingredient_seller", "action_name": "buy_meal_ingredients"})
    env.step({"type": "move_to", "target_id": "workshop_lobby"})
    env.step({"type": "move_to", "target_id": "meal_prep_room"})
    env.step({"type": "call_action", "target_id": "meal_prep_table", "action_name": "assemble_meal_box"})
    env.step({"type": "move_to", "target_id": "workshop_lobby"})
    env.step({"type": "move_to", "target_id": "cafe_front"})
    env.step({"type": "move_to", "target_id": "pickup_window"})
    env.step({"type": "call_action", "target_id": "meal_counter", "action_name": "sell_meal_box"})


def _accept_repair_job_from_market(env: TownBenchEnv) -> None:
    env.step({"type": "move_to", "target_id": "plaza"})
    env.step({"type": "move_to", "target_id": "service_depot"})
    env.step({"type": "call_action", "target_id": "repair_queue", "action_name": "accept_repair_job"})
    env.step({"type": "move_to", "target_id": "plaza"})
    env.step({"type": "move_to", "target_id": "market"})


def _run_repair_loop_from_cafe(env: TownBenchEnv) -> None:
    env.step({"type": "move_to", "target_id": "cafe_front"})
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step(
        {
            "type": "call_action",
            "target_id": "supply_counter",
            "action_name": "buy",
            "args": {"item_id": "repair_part"},
        }
    )
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "workshop_lobby"})
    env.step({"type": "move_to", "target_id": "repair_room"})
    env.step({"type": "call_action", "target_id": "repair_bench", "action_name": "service_kettle"})
    env.step({"type": "move_to", "target_id": "workshop_lobby"})
    env.step({"type": "move_to", "target_id": "service_depot"})
    env.step({"type": "call_action", "target_id": "pickup_clerk", "action_name": "collect_service_fee"})


def test_multi_area_town_loads_expected_area_aware_content():
    env = _load_multi_area_env()
    observation = env.reset()

    assert env.state.scenario_id == "multi_area_town"
    assert observation.current_location.location_id == "plaza"
    assert observation.current_area is not None
    assert observation.current_area.area_id == "market_block"
    assert set(observation.nearby_locations) == {
        "market",
        "supply_shop",
        "fuel_counter",
        "workshop_lobby",
        "storage_room",
        "service_depot",
        "home_entry",
        "cafe_front",
    }
    assert set(env.state.areas) == {
        "market_block",
        "workshop_building",
        "service_hub",
        "home_block",
        "cafe_corner",
    }
    assert env.state.locations["tea_room"].area_id == "workshop_building"
    assert env.state.locations["pickup_window"].area_id == "cafe_corner"
    assert env.state.objects["operations_board"].resource_content.startswith("Town operating summary")
    assert "repair_job_accepted" in env.state.world_flags
    assert env.state.objects["cafe_buyer"].visible_state["packed_tea_payout"] == 12
    assert env.state.objects["locker_desk"].visible_state["upgrade_status"] == "available"
    assert "accept_repair_job" in env.state.objects["repair_queue"].callable_actions
    assert [rule.rule_id for rule in env.state.dynamic_rules] == [
        "early_fuel_discount",
        "breakfast_meal_bonus",
        "morning_packed_tea_bonus",
        "morning_repair_premium",
        "depot_lunch_break",
        "repair_queue_intake_closed",
    ]


def test_multi_area_town_tea_loop_can_repeat_profitably():
    env = _load_multi_area_env()
    env.reset()
    env.step({"type": "move_to", "target_id": "market"})

    _run_tea_loop(env)
    _run_tea_loop(env)

    assert env.state.agent.money == 33
    assert env.state.agent.inventory == {}
    assert env.state.agent.location_id == "market"


def test_multi_area_town_packaging_requires_exact_room():
    env = _load_multi_area_env()
    env.reset()
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "call_action", "target_id": "tea_wholesaler", "action_name": "buy_tea_bundle"})
    env.step({"type": "move_to", "target_id": "fuel_counter"})
    env.step({"type": "call_action", "target_id": "fuel_rack", "action_name": "buy_fuel_canister"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step(
        {
            "type": "call_action",
            "target_id": "supply_counter",
            "action_name": "buy",
            "args": {"item_id": "packaging_sleeve"},
        }
    )
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "workshop_lobby"})
    env.step({"type": "move_to", "target_id": "tea_room"})
    env.step({"type": "call_action", "target_id": "tea_station", "action_name": "brew_tea"})

    blocked_pack = env.step({"type": "call_action", "target_id": "packaging_table", "action_name": "pack_tea"})

    env.step({"type": "move_to", "target_id": "packing_room"})
    successful_pack = env.step({"type": "call_action", "target_id": "packaging_table", "action_name": "pack_tea"})

    assert blocked_pack.success is False
    assert blocked_pack.warnings == ["not_accessible"]
    assert successful_pack.success is True
    assert env.state.agent.inventory == {"packed_tea": 1}


def test_multi_area_town_meal_loop_is_low_capital_fallback():
    env = _load_multi_area_env()
    env.reset()
    env.state.agent.money = 2
    env.step({"type": "move_to", "target_id": "market"})

    _run_meal_loop(env)

    assert env.state.agent.money == 7
    assert env.state.agent.inventory == {}
    assert env.state.agent.location_id == "pickup_window"


def test_multi_area_town_repair_loop_requires_more_startup_capital_than_meal_loop():
    env = _load_multi_area_env()
    env.reset()
    env.state.agent.money = 5
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})

    early_repair = env.step(
        {
            "type": "call_action",
            "target_id": "supply_counter",
            "action_name": "buy",
            "args": {"item_id": "repair_part"},
        }
    )
    env.step({"type": "move_to", "target_id": "market"})
    _accept_repair_job_from_market(env)
    _run_meal_loop(env)
    _run_repair_loop_from_cafe(env)

    assert early_repair.success is False
    assert early_repair.warnings == ["insufficient_money"]
    assert env.state.agent.money == 18
    assert env.state.agent.inventory == {}
    assert env.state.agent.location_id == "service_depot"
    assert env.state.world_flags["repair_job_accepted"] is False


def test_multi_area_town_locker_upgrade_enables_bulk_input_purchase_and_is_one_time():
    env = _load_multi_area_env()
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


def test_multi_area_town_home_recovery_consumes_meal_box():
    env = _load_multi_area_env()
    env.reset()
    env.state.agent.location_id = "kitchen"
    env.state.agent.energy = 10
    env.state.agent.inventory = {"meal_box": 1}

    recovery = env.step({"type": "call_action", "target_id": "pantry_shelf", "action_name": "eat_meal_box"})

    assert recovery.success is True
    assert env.state.agent.energy == 26
    assert env.state.agent.inventory == {}


def test_multi_area_town_sleep_shift_recovers_energy_without_money():
    env = _load_multi_area_env()
    env.reset()
    env.state.agent.location_id = "bedroom"
    env.state.agent.money = 0
    env.state.agent.energy = 10

    recovery = env.step({"type": "call_action", "target_id": "bed", "action_name": "sleep_shift"})

    assert recovery.success is True
    assert env.state.agent.money == 0
    assert env.state.agent.energy == 46


def test_multi_area_town_cafe_coffee_and_alt_sale_work():
    env = _load_multi_area_env()
    env.reset()
    env.state.agent.location_id = "coffee_counter"
    env.state.agent.money = 10
    env.state.agent.energy = 10

    coffee = env.step({"type": "call_action", "target_id": "barista", "action_name": "buy_coffee"})

    assert coffee.success is True
    assert env.state.agent.money == 7
    assert env.state.agent.energy == 22

    env.state.agent.location_id = "pickup_window"
    env.state.agent.money = 0
    env.state.agent.inventory = {"packed_tea": 1}
    sale = env.step({"type": "call_action", "target_id": "cafe_buyer", "action_name": "sell_packed_tea"})

    assert sale.success is True
    assert env.state.agent.money == 12
    assert env.state.agent.inventory == {}
    assert env.state.objects["goods_buyer"].visible_state["packed_tea_payout"] > sale.data["money"]


def test_multi_area_town_repair_intake_closes_after_morning_window():
    env = _load_multi_area_env()
    env.reset()
    env.state.current_time = parse_time_label("Day 1, 09:15")
    env.state.agent.location_id = "service_depot"

    result = env.step({"type": "call_action", "target_id": "repair_queue", "action_name": "accept_repair_job"})

    assert result.success is False
    assert result.warnings == ["action_temporarily_unavailable"]
    queue = next(item for item in result.observation.visible_objects if item.object_id == "repair_queue")
    assert queue.visible_state["intake_open"] is False


def test_multi_area_town_depot_lunch_break_temporarily_blocks_payout():
    env = _load_multi_area_env()
    env.reset()
    env.state.current_time = parse_time_label("Day 1, 11:45")
    env.state.agent.location_id = "service_depot"
    env.state.agent.inventory = {"serviced_device_ticket": 1}

    lunch_result = env.step({"type": "call_action", "target_id": "pickup_clerk", "action_name": "collect_service_fee"})

    env.state.current_time = parse_time_label("Day 1, 13:00")
    after_lunch_result = env.step(
        {"type": "call_action", "target_id": "pickup_clerk", "action_name": "collect_service_fee"}
    )

    assert lunch_result.success is False
    assert lunch_result.warnings == ["action_temporarily_unavailable"]
    assert after_lunch_result.success is True
    assert env.state.agent.money == 30
    assert env.state.agent.inventory == {}
