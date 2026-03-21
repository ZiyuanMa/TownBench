from runtime.env import TownBenchEnv
from engine.state import AgentState, Area, Location, WorldState


def test_observation_only_shows_current_location_objects(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)

    observation = env.reset()

    visible_ids = [item.object_id for item in observation.visible_objects]
    assert visible_ids == ["bulletin"]
    assert "counter" not in visible_ids


def test_world_state_area_defaults_and_round_trip_preserve_areas():
    state = WorldState(
        agent=AgentState(location_id="plaza"),
        locations={
            "plaza": Location(
                location_id="plaza",
                name="Plaza",
                description="The center square.",
            )
        },
    )
    dumped = state.model_dump()
    restored = WorldState.model_validate(dumped)
    copied = restored.model_copy(deep=True)

    assert state.locations["plaza"].area_id is None
    assert state.areas == {}
    assert restored.areas == {}
    copied.areas["town_center"] = Area(area_id="town_center", name="Town Center")

    assert restored.areas == {}
    assert copied.areas["town_center"].name == "Town Center"


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


def test_observation_projects_current_area_metadata(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.areas = {
        "town_center": Area(
            area_id="town_center",
            name="Town Center",
            description="The civic core.",
            tags=["public"],
        )
    }
    state.locations["plaza"].area_id = "town_center"
    env = TownBenchEnv(state)

    observation = env.reset()

    assert observation.current_area is not None
    assert observation.current_area.area_id == "town_center"
    assert observation.current_area.name == "Town Center"
    assert observation.current_area.tags == ["public"]


def test_observation_current_area_is_none_when_location_has_no_area(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)

    observation = env.reset()

    assert observation.current_area is None
    assert observation.nearby_locations == ["market"]


def test_observation_nearby_locations_include_same_area_and_explicit_links(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.areas = {
        "library": Area(area_id="library", name="Library"),
        "town_center": Area(area_id="town_center", name="Town Center"),
    }
    state.locations["plaza"].area_id = "library"
    state.locations["plaza"].links = ["reading_room", "market"]
    state.locations["reading_room"] = Location(
        location_id="reading_room",
        name="Reading Room",
        description="A public study room.",
        area_id="library",
    )
    state.locations["archive"] = Location(
        location_id="archive",
        name="Archive",
        description="A closed archive room.",
        area_id="library",
    )
    state.locations["market"].area_id = "town_center"
    env = TownBenchEnv(state)

    observation = env.reset()

    assert observation.current_location.links == ["reading_room", "market"]
    assert observation.nearby_locations == ["archive", "market", "reading_room"]


def test_observation_same_area_does_not_expand_visible_objects(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.areas = {"market_block": Area(area_id="market_block", name="Market Block")}
    state.locations["plaza"].area_id = "market_block"
    state.locations["market"].area_id = "market_block"
    env = TownBenchEnv(state)

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
