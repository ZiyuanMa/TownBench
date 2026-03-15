from runtime.env import TownBenchEnv


def test_reset_returns_initial_observation(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)

    observation = env.reset()

    assert observation.current_location.location_id == "plaza"
    assert [item.object_id for item in observation.visible_objects] == ["bulletin"]
    assert [item.skill_id for item in observation.visible_skills] == ["safety_basics"]
    assert env.get_trace() == []
    assert env.is_done() is False


def test_env_writes_trace_after_step(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "check_status"})

    assert result.success is True
    trace = env.get_trace()
    assert len(trace) == 1
    assert trace[0].step_id == 1
    assert trace[0].normalized_action["type"] == "check_status"
