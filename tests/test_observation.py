from runtime.env import TownBenchEnv


def test_observation_only_shows_current_location_objects(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)

    observation = env.reset()

    visible_ids = [item.object_id for item in observation.visible_objects]
    assert visible_ids == ["bulletin"]
    assert "counter" not in visible_ids


def test_inspect_requires_current_location_access(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    success_result = env.step({"type": "inspect", "target_id": "bulletin"})
    failure_result = env.step({"type": "inspect", "target_id": "counter"})

    assert success_result.success is True
    assert success_result.data["kind"] == "object"
    assert success_result.data["object"]["object_id"] == "bulletin"
    assert failure_result.success is False
    assert env.get_trace()[-1].error_type == "not_accessible"
