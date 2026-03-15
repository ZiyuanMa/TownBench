from runtime.env import TownBenchEnv


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
