from pathlib import Path

from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def _load_phase1_env() -> TownBenchEnv:
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "phase1_town" / "scenario.yaml"
    return TownBenchEnv(load_scenario(scenario_path))


def test_phase1_scenario_loads_expected_economic_content():
    env = _load_phase1_env()
    observation = env.reset()

    assert env.state.scenario_id == "phase1_town"
    assert observation.current_location.location_id == "plaza"
    assert set(env.state.locations) == {
        "plaza",
        "library",
        "market",
        "workshop",
        "canteen",
        "station",
        "supply_shop",
    }
    assert set(env.state.skills) == {
        "delivery_basics",
        "tea_basics",
        "market_observation",
        "town_history",
    }
    assert env.state.objects["job_board"].resource_content.startswith("Public work notice")
    assert env.state.objects["trade_notes"].resource_content.startswith("Trade notes copied")
    assert env.state.objects["general_buyer"].visible_state["packed_tea_payout"] == 17
    assert env.state.termination_config.max_steps == 20


def test_phase1_delivery_loop_pays_and_reopens_the_public_job():
    env = _load_phase1_env()
    env.reset()

    accept_result = env.step(
        {"type": "call_action", "target_id": "job_board", "action_name": "accept_delivery_run"}
    )
    env.step({"type": "move_to", "target_id": "station"})
    deliver_result = env.step(
        {"type": "call_action", "target_id": "parcel_locker", "action_name": "deliver_parcel"}
    )

    assert accept_result.success is True
    assert deliver_result.success is True
    assert deliver_result.money_delta == 5
    assert env.state.agent.money == 17
    assert env.state.agent.inventory == {}
    assert env.state.world_flags["delivery_job_open"] is True
    assert env.state.world_flags["delivery_job_active"] is False
    assert env.state.objects["job_board"].visible_state["latest_job"] == "Parcel run to the station pays 5 coins."


def test_phase1_tea_loop_requires_the_tool_investment_and_then_turns_profitable():
    env = _load_phase1_env()
    env.reset()

    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "call_action", "target_id": "tea_vendor", "action_name": "buy_tea_bundle"})
    env.step({"type": "move_to", "target_id": "workshop"})
    env.step({"type": "call_action", "target_id": "tea_station", "action_name": "brew_tea"})
    early_pack = env.step({"type": "call_action", "target_id": "packaging_table", "action_name": "pack_tea"})

    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    buy_kit = env.step(
        {
            "type": "call_action",
            "target_id": "tool_rack",
            "action_name": "buy",
            "args": {"item_id": "packaging_kit"},
        }
    )
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "workshop"})
    packed = env.step({"type": "call_action", "target_id": "packaging_table", "action_name": "pack_tea"})
    env.step({"type": "move_to", "target_id": "market"})
    sold = env.step({"type": "call_action", "target_id": "general_buyer", "action_name": "sell_packed_tea"})

    assert early_pack.success is False
    assert early_pack.warnings == ["missing_inventory"]
    assert buy_kit.success is True
    assert buy_kit.triggered_events == ["packaging_kit_notice"]
    assert packed.success is True
    assert sold.success is True
    assert env.state.agent.money == 21
    assert env.state.agent.inventory == {"packaging_kit": 1}
    assert env.state.world_flags["packaging_kit_owned"] is True
    assert env.state.objects["tool_rack"].visible_state["packaging_kit_status"] == "sold_to_current_agent"


def test_phase1_trade_notes_support_the_repair_contract_loop():
    env = _load_phase1_env()
    env.reset()

    env.step({"type": "move_to", "target_id": "library"})
    notes_result = env.step({"type": "open_resource", "target_id": "trade_notes"})
    env.step({"type": "move_to", "target_id": "plaza"})
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "supply_shop"})
    env.step(
        {
            "type": "call_action",
            "target_id": "tool_rack",
            "action_name": "buy",
            "args": {"item_id": "repair_kit"},
        }
    )
    env.step({"type": "move_to", "target_id": "market"})
    env.step({"type": "move_to", "target_id": "workshop"})
    repair_result = env.step(
        {"type": "call_action", "target_id": "repair_corner", "action_name": "service_commuter_kettle"}
    )

    assert notes_result.success is True
    assert "commuter kettle contract worth 15 coins" in notes_result.data["content"]
    assert repair_result.success is True
    assert repair_result.money_delta == 15
    assert env.state.agent.money == 22
    assert env.state.agent.inventory == {}


def test_phase1_spending_sinks_can_convert_cash_into_speed_and_recovery():
    env = _load_phase1_env()
    env.reset()

    env.step({"type": "move_to", "target_id": "station"})
    cart_result = env.step(
        {
            "type": "call_action",
            "target_id": "express_cart",
            "action_name": "ride",
            "args": {"destination": "market"},
        }
    )
    env.step({"type": "move_to", "target_id": "canteen"})
    meal_result = env.step({"type": "call_action", "target_id": "meal_counter", "action_name": "buy_hot_meal"})

    assert cart_result.success is True
    assert cart_result.data["location_id"] == "market"
    assert meal_result.success is True
    assert meal_result.money_delta == -5
    assert meal_result.energy_delta == 24
    assert env.state.agent.location_id == "canteen"
    assert env.state.agent.money == 6
    assert env.state.agent.energy == 69
