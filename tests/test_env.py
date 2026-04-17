from runtime.env import TownBenchEnv


def test_reset_returns_initial_observation(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)

    observation = env.reset()

    assert observation.current_location.location_id == "plaza"
    assert [item.object_id for item in observation.visible_objects] == ["bulletin"]
    assert [item.skill_id for item in observation.visible_skills] == ["safety_basics"]
    assert observation.visible_skills[0].name == "Safety Basics"
    assert observation.visible_skills[0].description.startswith("Simple safety reminders")
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


def test_wait_counts_as_a_normal_step_for_done_state(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.termination_config.max_steps = 1
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "wait", "args": {"minutes": 15}})

    assert result.success is True
    assert result.done is True
    assert result.termination_reason == "max_steps_reached"
    assert env.is_done() is True
