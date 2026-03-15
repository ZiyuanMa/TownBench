from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def test_trace_records_deltas_and_triggered_events():
    from pathlib import Path

    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    env.step({"type": "move_to", "target_id": "workshop"})
    result = env.step({"type": "call_action", "target_id": "tea_station", "args": {"action": "brew_tea"}})

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
