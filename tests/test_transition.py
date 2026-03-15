from runtime.env import TownBenchEnv
from engine.state import ObjectActionEffect, WorldEventRule


def test_move_to_updates_agent_location(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "market"})

    assert result.success is True
    assert result.observation.current_location.location_id == "market"
    assert env.state.agent.location_id == "market"
    assert env.get_trace()[0].success is True


def test_invalid_move_is_structured_failure(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "warehouse"})

    assert result.success is False
    assert result.observation.current_location.location_id == "plaza"
    assert env.state.agent.location_id == "plaza"
    assert env.get_trace()[0].error_type == "unknown_location"


def test_write_note_appends_note_and_status_reflects_it(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    write_result = env.step({"type": "write_note", "args": {"text": "buy apples"}})
    status_result = env.step({"type": "check_status"})

    assert write_result.success is True
    assert env.state.agent.notes == ["buy apples"]
    assert status_result.data["agent_status"]["notes"] == ["buy apples"]


def test_successful_steps_apply_time_and_energy_costs(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "market"})

    assert result.success is True
    assert result.time_delta == 10
    assert result.energy_delta == -2
    assert env.state.current_time == "Day 1, 08:10"
    assert env.state.agent.energy == 98


def test_failed_steps_do_not_apply_resource_deltas(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "warehouse"})

    assert result.success is False
    assert result.time_delta == 0
    assert result.energy_delta == 0
    assert env.state.current_time == "Day 1, 08:00"
    assert env.state.agent.energy == 100


def test_world_rules_and_success_termination_apply_after_action(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["buy_apple"]
    env.state.objects["counter"].action_effects = {
        "buy_apple": ObjectActionEffect(
            message="Purchased an apple.",
            set_visible_state={"sold_out": True},
            set_world_flags={"apple_bought": True},
        )
    }
    env.state.locations["market"].object_ids = ["counter"]
    env.state.event_rules = [
        WorldEventRule(
            event_id="apple_notice",
            required_world_flags={"apple_bought": True},
            set_world_flags={"errand_complete": True},
            set_object_visible_state={"counter": {"receipt_ready": True}},
            trigger_once=True,
        )
    ]
    env.state.termination_config.success_world_flags = ["errand_complete"]

    env.step({"type": "move_to", "target_id": "market"})
    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "buy_apple"}})

    assert result.success is True
    assert result.triggered_events == ["apple_notice"]
    assert result.done is True
    assert result.termination_reason == "success:errand_complete"
    assert env.state.world_flags["errand_complete"] is True
    assert env.state.objects["counter"].visible_state["receipt_ready"] is True
