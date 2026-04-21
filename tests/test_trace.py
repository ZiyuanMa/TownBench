from runtime.env import TownBenchEnv
from engine.state import (
    CallableActionDefinition,
    CallableActionRoute,
    ObjectActionEffect,
)
from scenario.loader import load_scenario


def test_trace_records_deltas_and_triggered_events():
    from pathlib import Path

    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})
    result = env.step({"type": "call_action", "target_id": "tea_station", "action_name": "brew_tea"})

    trace = env.get_trace()
    assert result.triggered_events == ["tea_ready_notice"]
    assert trace[-1].time_delta == 10
    assert trace[-1].energy_delta == -4
    assert trace[-1].triggered_events == ["tea_ready_notice"]
    assert trace[-1].inventory_delta == {}


def test_trace_records_termination_state(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.termination_config.max_steps = 1

    result = env.step({"type": "check_status"})

    trace = env.get_trace()
    assert result.done is True
    assert result.termination_reason == "max_steps_reached"
    assert trace[-1].done is True
    assert trace[-1].termination_reason == "max_steps_reached"


def test_trace_records_money_delta_from_object_actions(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "sell_snack": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Sold a snack.",
                        money_delta=5,
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})
    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "sell_snack"})

    trace = env.get_trace()
    assert result.money_delta == 5
    assert trace[-1].money_delta == 5


def test_trace_records_object_inventory_and_energy_deltas(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_supply": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought one supply crate.",
                        money_delta=-3,
                        energy_delta=6,
                        inventory_delta={"supply_crate": 1},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_supply"})

    trace = env.get_trace()
    assert result.inventory_delta == {"supply_crate": 1}
    assert result.energy_delta == 3
    assert trace[-1].inventory_delta == {"supply_crate": 1}
    assert trace[-1].energy_delta == 3
