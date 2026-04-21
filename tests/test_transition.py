from runtime.env import TownBenchEnv
from engine.state import (
    ActionCost,
    Area,
    CallableActionArgumentSpec,
    CallableActionDefinition,
    CallableActionMatcher,
    CallableActionOverrideRule,
    CallableActionRoute,
    DynamicCondition,
    DynamicRule,
    DynamicRuleApplication,
    Location,
    ObjectActionEffect,
    ObjectDynamicOverride,
    TimeWindow,
    WorldEventRule,
)


def test_move_to_updates_agent_location(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "market"})

    assert result.success is True
    assert result.observation.current_location.location_id == "market"
    assert env.state.agent.location_id == "market"
    assert env.get_trace()[0].success is True


def test_move_to_current_location_is_a_successful_no_op(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()

    result = env.step({"type": "move_to", "target_id": "plaza"})

    assert result.success is True
    assert result.observation.current_location.location_id == "plaza"
    assert env.state.agent.location_id == "plaza"
    assert result.time_delta == 10
    assert result.energy_delta == -2
    assert env.state.current_time == 8 * 60 + 10


def test_invalid_move_is_structured_failure(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "warehouse"})

    assert result.success is False
    assert result.observation.current_location.location_id == "plaza"
    assert env.state.agent.location_id == "plaza"
    assert env.get_trace()[0].error_type == "unknown_location"


def test_non_snapshot_tools_keep_their_existing_payloads(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["bulletin"].readable = True
    env.state.objects["bulletin"].resource_content = "Town market opens at eight."

    check_status = env.step({"type": "check_status"})
    inspect_result = env.step({"type": "inspect", "target_id": "plaza"})
    open_resource = env.step({"type": "open_resource", "target_id": "bulletin"})

    assert check_status.data["agent_status"]["location_id"] == "plaza"
    assert inspect_result.data["kind"] == "location"
    assert open_resource.data["object_id"] == "bulletin"


def test_wait_advances_time_without_other_state_changes(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()

    result = env.step({"type": "wait", "args": {"minutes": 30}})

    assert result.success is True
    assert result.time_delta == 30
    assert result.money_delta == 0
    assert result.energy_delta == 0
    assert env.state.current_time == (8 * 60) + 30
    assert env.state.agent.location_id == "plaza"
    assert env.state.agent.money == 20
    assert env.state.agent.energy == 100
    assert result.observation.current_time == "Day 1, 08:30"
    assert env.get_trace()[0].success is True


def test_wait_rejects_invalid_durations(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()

    zero_result = env.step({"type": "wait", "args": {"minutes": 0}})
    long_result = env.step({"type": "wait", "args": {"minutes": 241}})

    assert zero_result.success is False
    assert zero_result.warnings == ["invalid_wait_duration"]
    assert long_result.success is False
    assert long_result.warnings == ["invalid_wait_duration"]
    assert env.state.current_time == 8 * 60


def test_wait_preserves_scenario_defined_non_time_costs(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.inventory = {"apple": 1}
    state.action_costs["wait"] = ActionCost(
        time_delta=5,
        money_delta=-2,
        energy_delta=-7,
        inventory_delta={"apple": -1},
    )
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "wait", "args": {"minutes": 30}})

    assert result.success is True
    assert result.time_delta == 30
    assert result.money_delta == -2
    assert result.energy_delta == -7
    assert result.inventory_delta == {"apple": -1}
    assert env.state.current_time == (8 * 60) + 30
    assert env.state.agent.money == 18
    assert env.state.agent.energy == 93
    assert env.state.agent.inventory == {}


def test_move_to_allows_same_area_locations_without_explicit_links(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.areas = {
        "market_block": Area(area_id="market_block", name="Market Block"),
    }
    state.agent.location_id = "market"
    state.locations["market"].area_id = "market_block"
    state.locations["market"].links = []
    state.locations["storeroom"] = Location(
        location_id="storeroom",
        name="Storeroom",
        description="A back room.",
        area_id="market_block",
    )
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "storeroom"})

    assert result.success is True
    assert env.state.agent.location_id == "storeroom"


def test_move_to_requires_explicit_link_across_areas(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.areas = {
        "town_center": Area(area_id="town_center", name="Town Center"),
        "market_block": Area(area_id="market_block", name="Market Block"),
    }
    state.agent.location_id = "market"
    state.locations["plaza"].area_id = "town_center"
    state.locations["market"].area_id = "market_block"
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "plaza"})

    assert result.success is True
    assert env.state.agent.location_id == "plaza"


def test_move_to_rejects_existing_cross_area_location_without_link(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.areas = {
        "market_block": Area(area_id="market_block", name="Market Block"),
        "service_hub": Area(area_id="service_hub", name="Service Hub"),
    }
    state.agent.location_id = "market"
    state.locations["market"].area_id = "market_block"
    state.locations["market"].links = []
    state.locations["depot"] = Location(
        location_id="depot",
        name="Depot",
        description="A service depot.",
        area_id="service_hub",
    )
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "depot"})

    assert result.success is False
    assert result.warnings == ["unreachable_location"]
    assert env.state.agent.location_id == "market"


def test_move_to_without_areas_still_depends_only_on_links(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.locations["warehouse"] = Location(
        location_id="warehouse",
        name="Warehouse",
        description="A storage building.",
    )
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "warehouse"})

    assert result.success is False
    assert result.warnings == ["unreachable_location"]
    assert env.state.agent.location_id == "plaza"


def test_check_status_returns_structured_agent_status_payload(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.inventory = {"apple": 2}
    env.state.agent.status_effects = ["focused"]
    env.state.agent.stats = {"carry_limit": 3}

    result = env.step({"type": "check_status"})

    assert result.success is True
    assert result.data["agent_status"] == {
        "current_time": "Day 1, 08:00",
        "location_id": "plaza",
        "money": 20,
        "energy": 100,
        "inventory": {"apple": 2},
        "status_effects": ["focused"],
        "stats": {"carry_limit": 3},
    }


def test_call_action_required_agent_stats_blocks_execution(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 2}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "lift_crate": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Lifted the crate.",
                        required_agent_stats={"carry_limit": 3},
                        set_visible_state={"crate_moved": True},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "lift_crate"})

    assert result.success is False
    assert result.warnings == ["missing_prerequisites"]
    assert env.state.agent.stats == {"carry_limit": 2}
    assert env.state.objects["counter"].visible_state == {"open": True}


def test_call_action_accepts_top_level_action_name(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 2}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "rent_cart": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Rented a hand cart.",
                        money_delta=-4,
                        required_money=4,
                        agent_stat_deltas={"carry_limit": 3},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "action_name": "rent_cart",
        }
    )

    assert result.success is True
    assert result.data["action_name"] == "rent_cart"
    assert env.state.agent.stats == {"carry_limit": 5}


def test_call_action_rejects_missing_action_name_in_args(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "rent_cart": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Rented a hand cart.",
                        money_delta=-4,
                        required_money=4,
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "rent_cart"}})

    assert result.success is False
    assert result.warnings == ["missing_action_name"]


def test_call_action_can_resolve_parameterized_object_action(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy": CallableActionDefinition(
            description="Buy one item from the counter.",
            arguments={
                "item_id": CallableActionArgumentSpec(options=["snack", "drink"]),
            },
            routes=[
                CallableActionRoute(
                    match={"item_id": "snack"},
                    effect=ObjectActionEffect(message="Bought a snack.", money_delta=-3, required_money=3),
                ),
                CallableActionRoute(
                    match={"item_id": "drink"},
                    effect=ObjectActionEffect(message="Bought a drink.", money_delta=-2, required_money=2),
                ),
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "action_name": "buy",
            "args": {"item_id": "snack"},
        }
    )

    assert result.success is True
    assert result.data["action_name"] == "buy"
    assert result.data["action_args"] == {"item_id": "snack"}
    assert env.state.agent.money == 17


def test_call_action_parameterized_action_requires_action_args(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy": CallableActionDefinition(
            arguments={
                "item_id": CallableActionArgumentSpec(options=["snack", "drink"]),
            },
            routes=[
                CallableActionRoute(match={"item_id": "snack"}, effect=ObjectActionEffect(message="Bought a snack.")),
                CallableActionRoute(match={"item_id": "drink"}, effect=ObjectActionEffect(message="Bought a drink.")),
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy"})

    assert result.success is False
    assert result.warnings == ["missing_action_args"]


def test_call_action_parameterized_action_rejects_invalid_action_args(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy": CallableActionDefinition(
            arguments={
                "item_id": CallableActionArgumentSpec(options=["snack", "drink"]),
            },
            routes=[
                CallableActionRoute(match={"item_id": "snack"}, effect=ObjectActionEffect(message="Bought a snack.")),
                CallableActionRoute(match={"item_id": "drink"}, effect=ObjectActionEffect(message="Bought a drink.")),
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "action_name": "buy",
            "args": {"item_id": "apple"},
        }
    )

    assert result.success is False
    assert result.warnings == ["invalid_action_args"]


def test_call_action_agent_stat_deltas_update_state_and_payload(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 2}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "rent_cart": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Rented a hand cart.",
                        money_delta=-4,
                        required_money=4,
                        agent_stat_deltas={"carry_limit": 3},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "rent_cart"})

    assert result.success is True
    assert env.state.agent.stats == {"carry_limit": 5}
    assert result.data["stats"] == {"carry_limit": 5}


def test_call_action_can_reduce_carry_limit_to_zero_without_dropping_the_stat(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "disable_bag": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Disabled the bag.",
                        agent_stat_deltas={"carry_limit": -1},
                    ),
                )
            ],
        ),
        "load_item": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Tried to load one item.",
                        inventory_delta={"apple": 1},
                    ),
                )
            ],
        ),
    }
    env.step({"type": "move_to", "target_id": "market"})

    disabled = env.step({"type": "call_action", "target_id": "counter", "action_name": "disable_bag"})
    blocked = env.step({"type": "call_action", "target_id": "counter", "action_name": "load_item"})

    assert disabled.success is True
    assert env.state.agent.stats == {"carry_limit": 0}
    assert disabled.data["stats"] == {"carry_limit": 0}
    assert blocked.success is False
    assert blocked.warnings == ["inventory_capacity_exceeded"]
    assert env.state.agent.inventory == {}


def test_call_action_clamps_negative_carry_limit_to_zero(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "over_disable_bag": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Over-disabled the bag.",
                        agent_stat_deltas={"carry_limit": -2},
                    ),
                )
            ],
        ),
        "check_zero_gate": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Zero-capacity gate passed.",
                        required_agent_stats={"carry_limit": 0},
                    ),
                )
            ],
        ),
    }
    env.step({"type": "move_to", "target_id": "market"})

    disabled = env.step({"type": "call_action", "target_id": "counter", "action_name": "over_disable_bag"})
    gated = env.step({"type": "call_action", "target_id": "counter", "action_name": "check_zero_gate"})

    assert disabled.success is True
    assert env.state.agent.stats == {"carry_limit": 0}
    assert disabled.data["stats"] == {"carry_limit": 0}
    assert gated.success is True


def test_call_action_reports_temporarily_unavailable_when_disabled_by_dynamic_rule(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.objects["counter"].actionable = True
    state.objects["counter"].callable_actions = {
        "buy_snack": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought a snack.",
                        required_money=2,
                        money_delta=-2,
                        inventory_delta={"snack": 1},
                    ),
                )
            ],
        )
    }
    state.objects["counter"].visible_state = {"open": True}
    state.dynamic_rules = [
        DynamicRule(
            rule_id="counter_closed_early",
            when=DynamicCondition(time_window=TimeWindow(start="17:00", end="08:30")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"open": False},
                        disabled_callable_actions=[
                            CallableActionMatcher(action_name="buy_snack"),
                        ],
                    )
                }
            ),
        )
    ]
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_snack"})

    assert result.success is False
    assert result.warnings == ["action_temporarily_unavailable"]
    assert result.data["current_time"] == "Day 1, 08:00"
    assert result.data["dynamic_reason"] == "disabled_by_dynamic_rule"
    assert result.data["visible_state"] == {"open": False}


def test_call_action_can_run_when_higher_priority_rule_reenables_action(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.agent.money = 5
    state.current_time = (9 * 60) + 15
    state.objects["counter"].actionable = True
    state.objects["counter"].callable_actions = {
        "buy_snack": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought a snack.",
                        required_money=2,
                        money_delta=-2,
                        inventory_delta={"snack": 1},
                    ),
                )
            ],
        )
    }
    state.objects["counter"].visible_state = {"open": True}
    state.dynamic_rules = [
        DynamicRule(
            rule_id="counter_closed",
            priority=0,
            when=DynamicCondition(time_window=TimeWindow(start="08:00", end="12:00")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"open": False},
                        disabled_callable_actions=[
                            CallableActionMatcher(action_name="buy_snack"),
                        ],
                    )
                }
            ),
        ),
        DynamicRule(
            rule_id="snack_window",
            priority=10,
            when=DynamicCondition(time_window=TimeWindow(start="09:00", end="10:00")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"open": True, "special_window": True},
                        enabled_callable_actions=[
                            CallableActionMatcher(action_name="buy_snack"),
                        ],
                    )
                }
            ),
        ),
    ]
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_snack"})

    assert result.success is True
    assert result.message == "Bought a snack."
    assert result.data["inventory"] == {"snack": 1}
    assert result.data["visible_state"] == {"open": True, "special_window": True}


def test_inspect_returns_detached_object_payload(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()

    result = env.step({"type": "inspect", "target_id": "bulletin"})
    payload_object = result.data["object"]
    payload_object["visible_state"]["notice_count"] = 99

    assert result.success is True
    assert result.data["kind"] == "object"
    assert payload_object["object_id"] == "bulletin"
    assert env.state.objects["bulletin"].visible_state["notice_count"] == 2


def test_open_resource_returns_resource_payload(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["bulletin"].readable = True
    env.state.objects["bulletin"].resource_content = "Market closes at noon."

    result = env.step({"type": "open_resource", "target_id": "bulletin"})

    assert result.success is True
    assert result.data == {
        "kind": "resource",
        "object_id": "bulletin",
        "title": "Bulletin Board",
        "content": "Market closes at noon.",
    }
def test_successful_steps_apply_time_and_energy_costs(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "market"})

    assert result.success is True
    assert result.time_delta == 10
    assert result.energy_delta == -2
    assert env.state.current_time == 8 * 60 + 10
    assert env.state.agent.energy == 98


def test_failed_steps_do_not_apply_resource_deltas(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "move_to", "target_id": "warehouse"})

    assert result.success is False
    assert result.time_delta == 0
    assert result.energy_delta == 0
    assert env.state.current_time == 8 * 60
    assert env.state.agent.energy == 100


def test_world_rules_and_success_termination_apply_after_action(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_apple": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Purchased an apple.",
                        set_visible_state={"sold_out": True},
                        set_world_flags={"apple_bought": True},
                    ),
                )
            ],
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
    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_apple"})

    assert result.success is True
    assert result.triggered_events == ["apple_notice"]
    assert result.done is True
    assert result.termination_reason == "success:errand_complete"
    assert env.state.world_flags["errand_complete"] is True
    assert env.state.objects["counter"].visible_state["receipt_ready"] is True


def test_event_rules_support_condition_dsl_composition(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_apple": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Purchased an apple.",
                        set_world_flags={"apple_bought": True},
                    ),
                )
            ],
        )
    }
    env.state.event_rules = [
        WorldEventRule(
            event_id="market_notice",
            when={
                "all": [
                    {"world_flags": {"apple_bought": True}},
                    {"location_id": "market"},
                ]
            },
            set_world_flags={"market_notice_ready": True},
            trigger_once=True,
        )
    ]

    env.step({"type": "move_to", "target_id": "market"})
    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_apple"})

    assert result.success is True
    assert result.triggered_events == ["market_notice"]
    assert env.state.world_flags["market_notice_ready"] is True


def test_call_action_can_apply_money_delta_and_reports_net_step_delta(minimal_world_state):
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
                        money_delta=7,
                        set_visible_state={"last_sale": "snack"},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "action_name": "sell_snack",
        }
    )

    assert result.success is True
    assert result.money_delta == 7
    assert env.state.agent.money == 27
    assert result.data["money"] == 27
    assert env.state.objects["counter"].visible_state["last_sale"] == "snack"


def test_inventory_capacity_is_unlimited_when_carry_limit_is_absent(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_bulk": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought a large bulk order.",
                        inventory_delta={"apple": 6},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_bulk"})

    assert result.success is True
    assert env.state.agent.inventory == {"apple": 6}


def test_object_action_inventory_delta_respects_carry_limit(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_bulk": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought a large bulk order.",
                        inventory_delta={"apple": 2},
                        set_visible_state={"sale": "closed"},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_bulk"})

    assert result.success is False
    assert result.warnings == ["inventory_capacity_exceeded"]
    assert env.state.agent.inventory == {}
    assert env.state.objects["counter"].visible_state == {"open": True}


def test_object_action_can_increase_carry_limit_and_add_inventory_in_same_step(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "upgrade_and_load": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Expanded the bag and loaded produce.",
                        agent_stat_deltas={"carry_limit": 1},
                        inventory_delta={"apple": 2},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "upgrade_and_load"})

    assert result.success is True
    assert env.state.agent.stats == {"carry_limit": 2}
    assert env.state.agent.inventory == {"apple": 2}


def test_capacity_decrease_is_validated_against_projected_carry_limit(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 3}
    env.state.agent.inventory = {"apple": 2}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "shrink_bag": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Shrank the bag.",
                        agent_stat_deltas={"carry_limit": -2},
                        set_visible_state={"bag_size": "small"},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "shrink_bag"})

    assert result.success is False
    assert result.warnings == ["inventory_capacity_exceeded"]
    assert env.state.agent.stats == {"carry_limit": 3}
    assert env.state.agent.inventory == {"apple": 2}
    assert env.state.objects["counter"].visible_state == {"open": True}


def test_action_cost_inventory_delta_respects_carry_limit(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 0}
    env.state.action_costs["check_status"] = ActionCost(inventory_delta={"apple": 1})

    result = env.step({"type": "check_status"})

    assert result.success is False
    assert result.warnings == ["inventory_capacity_exceeded"]
    assert result.inventory_delta == {}
    assert env.state.agent.inventory == {}


def test_unrelated_actions_do_not_soft_lock_invalid_over_capacity_runtime_state(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.agent.inventory = {"apple": 2}

    status_result = env.step({"type": "check_status"})
    move_result = env.step({"type": "move_to", "target_id": "market"})

    assert status_result.success is True
    assert status_result.data["agent_status"]["inventory"] == {"apple": 2}
    assert move_result.success is True
    assert env.state.agent.location_id == "market"


def test_call_action_inventory_validation_uses_net_step_delta(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.agent.inventory = {"apple": 1}
    env.state.action_costs["call_action"] = ActionCost(inventory_delta={"apple": -1})
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "swap_item": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Swapped the carried item.",
                        inventory_delta={"banana": 1},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "swap_item"})

    assert result.success is True
    assert result.inventory_delta == {"banana": 1, "apple": -1}
    assert env.state.agent.inventory == {"banana": 1}


def test_call_action_net_inventory_commit_uses_merged_delta_for_same_item(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.inventory = {"apple": 1}
    env.state.action_costs["call_action"] = ActionCost(inventory_delta={"apple": 1})
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "consume_and_rebate": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Consumed apples with a rebate.",
                        inventory_delta={"apple": -2},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "consume_and_rebate"})

    assert result.success is True
    assert result.inventory_delta == {"apple": -1}
    assert env.state.agent.inventory == {}


def test_call_action_money_validation_uses_net_step_delta(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.money = 1
    env.state.action_costs["call_action"] = ActionCost(money_delta=2)
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "rebated_fee": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Paid a fee with a matching rebate.",
                        money_delta=-2,
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "rebated_fee"})

    assert result.success is True
    assert result.money_delta == 0
    assert env.state.agent.money == 1


def test_combined_object_and_action_cost_inventory_delta_rolls_back_state(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.action_costs["call_action"] = ActionCost(inventory_delta={"bonus_ticket": 1})
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_box": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought one boxed order.",
                        inventory_delta={"apple": 1},
                        set_visible_state={"sale": "posted"},
                        set_world_flags={"box_bought": True},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_box"})

    assert result.success is False
    assert result.warnings == ["inventory_capacity_exceeded"]
    assert result.inventory_delta == {}
    assert env.state.agent.inventory == {}
    assert env.state.agent.money == 20
    assert env.state.world_flags == {}
    assert env.state.objects["counter"].visible_state == {"open": True}


def test_step_payload_visible_state_is_detached_from_runtime_state(minimal_world_state):
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
                        set_visible_state={"sale": {"item": "snack", "history": ["snack"]}},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "action_name": "sell_snack",
        }
    )
    payload_state = result.data["visible_state"]["sale"]
    payload_state["item"] = "tampered"
    payload_state["history"].append("tampered")

    assert env.state.objects["counter"].visible_state["sale"]["item"] == "snack"
    assert env.state.objects["counter"].visible_state["sale"]["history"] == ["snack"]


def test_invalid_action_still_counts_toward_termination(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.termination_config.max_steps = 1
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"bogus": 1})

    assert result.success is False
    assert result.done is True
    assert result.termination_reason == "max_steps_reached"
    assert env.is_done() is True
    assert env.get_trace()[0].error_type == "invalid_action"


def test_non_once_world_rules_only_trigger_on_state_change(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.world_flags["shift_open"] = True
    env.state.event_rules = [
        WorldEventRule(
            event_id="shift_notice",
            required_world_flags={"shift_open": True},
            set_object_visible_state={"bulletin": {"status": "open"}},
            trigger_once=False,
        )
    ]

    first_result = env.step({"type": "check_status"})
    second_result = env.step({"type": "check_status"})

    assert first_result.triggered_events == ["shift_notice"]
    assert second_result.triggered_events == []


def test_call_action_can_apply_energy_inventory_and_location_changes(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_ticket": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought a return ticket.",
                        required_money=6,
                        money_delta=-6,
                        energy_delta=5,
                        inventory_delta={"ticket": 1},
                        move_to_location_id="plaza",
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_ticket"})

    assert result.success is True
    assert result.money_delta == -6
    assert result.energy_delta == 2
    assert result.inventory_delta == {"ticket": 1}
    assert env.state.agent.location_id == "plaza"
    assert env.state.agent.money == 14
    assert env.state.agent.inventory == {"ticket": 1}
    assert result.data["location_id"] == "plaza"
    assert result.data["inventory"] == {"ticket": 1}
    assert result.observation.current_location.location_id == "plaza"
    assert result.observation.agent.inventory == {"ticket": 1}


def test_call_action_updates_observation_when_visible_state_changes_without_resource_deltas(
    minimal_world_state,
):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.action_costs["call_action"] = ActionCost()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "mark_sold": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Marked the counter as sold out.",
                        set_visible_state={"open": False, "sold_out": True},
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "mark_sold"})

    assert result.success is True
    assert result.energy_delta == 0
    assert [item.object_id for item in result.observation.visible_objects] == ["counter"]
    assert [item.action_name for item in result.observation.visible_objects[0].callable_actions] == ["mark_sold"]
    assert result.observation.visible_objects[0].visible_state == {"open": False, "sold_out": True}


def test_call_action_teleport_ignores_area_reachability(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.areas = {
        "market_block": Area(area_id="market_block", name="Market Block"),
        "service_hub": Area(area_id="service_hub", name="Service Hub"),
    }
    state.locations["market"].area_id = "market_block"
    state.locations["vault"] = Location(
        location_id="vault",
        name="Vault",
        description="A secured room.",
        area_id="service_hub",
    )
    env = TownBenchEnv(state)
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "enter_vault": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Escorted into the vault.",
                        move_to_location_id="vault",
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "enter_vault"})

    assert result.success is True
    assert env.state.agent.location_id == "vault"
    assert result.data["location_id"] == "vault"


def test_call_action_rejects_when_required_inventory_is_missing(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "repair_device": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Repaired device.",
                        required_inventory={"repair_kit": 1},
                        inventory_delta={"repair_kit": -1},
                        money_delta=9,
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "repair_device"})

    assert result.success is False
    assert result.warnings == ["missing_inventory"]
    assert env.state.agent.money == 20
    assert env.state.agent.inventory == {}


def test_call_action_rejects_when_money_would_drop_below_zero(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.money = 4
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].callable_actions = {
        "buy_machine": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(
                        message="Bought a machine.",
                        required_money=5,
                        money_delta=-5,
                    ),
                )
            ],
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "action_name": "buy_machine"})

    assert result.success is False
    assert result.warnings == ["insufficient_money"]
    assert env.state.agent.money == 4
