from runtime.env import TownBenchEnv


def test_observation_only_shows_current_location_objects(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)

    observation = env.reset()

    visible_ids = [item.object_id for item in observation.visible_objects]
    assert visible_ids == ["bulletin"]
    assert "counter" not in visible_ids


def test_observation_visible_state_is_detached_from_runtime_state(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.objects["bulletin"].visible_state = {
        "nested": {
            "status": "open",
            "tags": ["public"],
        }
    }
    env = TownBenchEnv(state)

    observation = env.reset()
    nested_state = observation.visible_objects[0].visible_state["nested"]
    nested_state["status"] = "closed"
    nested_state["tags"].append("changed")

    assert env.state.objects["bulletin"].visible_state["nested"]["status"] == "open"
    assert env.state.objects["bulletin"].visible_state["nested"]["tags"] == ["public"]


def test_observation_includes_agent_stats_and_detaches_them(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.stats = {"carry_limit": 4}
    env = TownBenchEnv(state)

    observation = env.reset()
    observation.agent.stats["carry_limit"] = 99

    assert observation.agent.stats == {"carry_limit": 99}
    assert env.state.agent.stats == {"carry_limit": 4}


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
