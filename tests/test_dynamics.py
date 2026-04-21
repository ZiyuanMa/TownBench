from engine.dynamics import build_effective_object_view, matches_time_window
from engine.rules import format_time_label, parse_time_label
from engine.state import (
    CallableActionDefinition,
    CallableActionMatcher,
    CallableActionOverrideRule,
    CallableActionRoute,
    DynamicCondition,
    DynamicRule,
    DynamicRuleApplication,
    ObjectActionEffect,
    ObjectDynamicOverride,
    TimeWindow,
)


def test_matches_time_window_supports_cross_midnight():
    window = TimeWindow(start="17:00", end="08:30")

    assert matches_time_window(parse_time_label("Day 1, 07:45"), window) is True
    assert matches_time_window(parse_time_label("Day 2, 07:45"), window) is True
    assert matches_time_window(parse_time_label("Day 1, 08:30"), window) is False
    assert matches_time_window(parse_time_label("Day 1, 16:59"), window) is False
    assert matches_time_window(parse_time_label("Day 1, 17:00"), window) is True


def test_time_labels_round_trip_through_integer_minutes():
    total_minutes = parse_time_label("Day 3, 09:15")

    assert total_minutes == (2 * 24 * 60) + (9 * 60) + 15
    assert format_time_label(total_minutes) == "Day 3, 09:15"


def test_effective_object_view_applies_overrides_without_mutating_base_state(minimal_world_state):
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
                    effect=ObjectActionEffect(message="Bought a snack.", required_money=3, money_delta=-3),
                )
            ],
        ),
        "buy_drink": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(message="Bought a drink.", required_money=2, money_delta=-2),
                )
            ],
        ),
    }
    state.objects["counter"].visible_state = {"open": True, "snack_price": 3}
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
        ),
        DynamicRule(
            rule_id="midmorning_discount",
            priority=10,
            when=DynamicCondition(time_window=TimeWindow(start="09:00", end="10:00")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"snack_price": 1},
                        callable_action_overrides=[
                            CallableActionOverrideRule(
                                match=CallableActionMatcher(action_name="buy_snack"),
                                override={
                                    "required_money": 1,
                                    "money_delta": -1,
                                },
                            )
                        ],
                    )
                }
            ),
        ),
    ]

    early_view = build_effective_object_view(state, "counter", at_time=8 * 60)
    assert early_view is not None
    assert early_view.object.visible_state == {"open": False, "snack_price": 3}
    assert list(early_view.object.callable_actions) == ["buy_drink"]

    discount_view = build_effective_object_view(state, "counter", at_time=(9 * 60) + 15)
    assert discount_view is not None
    assert discount_view.object.visible_state == {"open": True, "snack_price": 1}
    assert list(discount_view.object.callable_actions) == ["buy_snack", "buy_drink"]
    assert discount_view.object.callable_actions["buy_snack"].routes[0].effect.required_money == 1
    assert discount_view.object.callable_actions["buy_snack"].routes[0].effect.money_delta == -1

    assert state.objects["counter"].visible_state == {"open": True, "snack_price": 3}
    assert list(state.objects["counter"].callable_actions) == ["buy_snack", "buy_drink"]
    assert state.objects["counter"].callable_actions["buy_snack"].routes[0].effect.required_money == 3
    assert state.objects["counter"].callable_actions["buy_snack"].routes[0].effect.money_delta == -3


def test_higher_priority_rule_can_reenable_action(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.objects["counter"].actionable = True
    state.objects["counter"].callable_actions = {
        "buy_snack": CallableActionDefinition(
            description="",
            arguments={},
            routes=[CallableActionRoute(match={}, effect=ObjectActionEffect(message="Bought a snack."))],
        ),
        "buy_drink": CallableActionDefinition(
            description="",
            arguments={},
            routes=[CallableActionRoute(match={}, effect=ObjectActionEffect(message="Bought a drink."))],
        ),
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
                            CallableActionMatcher(action_name="buy_drink"),
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

    closed_view = build_effective_object_view(state, "counter", at_time=(8 * 60) + 30)
    assert closed_view is not None
    assert closed_view.object.visible_state == {"open": False}
    assert closed_view.object.callable_actions == {}
    assert {matcher.action_name for matcher in closed_view.disabled_routes} == {"buy_drink", "buy_snack"}

    reopened_view = build_effective_object_view(state, "counter", at_time=(9 * 60) + 15)
    assert reopened_view is not None
    assert reopened_view.object.visible_state == {"open": True, "special_window": True}
    assert list(reopened_view.object.callable_actions) == ["buy_snack"]
    assert tuple(matcher.action_name for matcher in reopened_view.disabled_routes) == ("buy_drink",)


def test_higher_priority_disable_keeps_action_closed_even_if_lower_priority_rule_enabled_it(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.objects["counter"].actionable = True
    state.objects["counter"].callable_actions = {
        "buy_snack": CallableActionDefinition(
            description="",
            arguments={},
            routes=[CallableActionRoute(match={}, effect=ObjectActionEffect(message="Bought a snack."))],
        ),
    }
    state.objects["counter"].visible_state = {"open": True}
    state.dynamic_rules = [
        DynamicRule(
            rule_id="early_promo",
            priority=0,
            when=DynamicCondition(time_window=TimeWindow(start="08:00", end="12:00")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        enabled_callable_actions=[
                            CallableActionMatcher(action_name="buy_snack"),
                        ]
                    )
                }
            ),
        ),
        DynamicRule(
            rule_id="late_closure",
            priority=10,
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
    ]

    effective_view = build_effective_object_view(state, "counter", at_time=(9 * 60))

    assert effective_view is not None
    assert effective_view.object.visible_state == {"open": False}
    assert effective_view.object.callable_actions == {}
    assert tuple(matcher.action_name for matcher in effective_view.disabled_routes) == ("buy_snack",)


def test_wait_updates_dynamic_observation_window(minimal_world_state):
    from runtime.env import TownBenchEnv

    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.current_time = (8 * 60) + 45
    state.objects["counter"].actionable = True
    state.objects["counter"].callable_actions = {
        "buy_snack": CallableActionDefinition(
            description="",
            arguments={},
            routes=[
                CallableActionRoute(
                    match={},
                    effect=ObjectActionEffect(message="Bought a snack.", required_money=3, money_delta=-3),
                )
            ],
        ),
    }
    state.objects["counter"].visible_state = {"open": True, "snack_price": 3}
    state.dynamic_rules = [
        DynamicRule(
            rule_id="midmorning_discount",
            priority=10,
            when=DynamicCondition(time_window=TimeWindow(start="09:00", end="10:00")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"snack_price": 1},
                        callable_action_overrides=[
                            CallableActionOverrideRule(
                                match=CallableActionMatcher(action_name="buy_snack"),
                                override={
                                    "required_money": 1,
                                    "money_delta": -1,
                                },
                            )
                        ],
                    )
                }
            ),
        ),
    ]
    env = TownBenchEnv(state)
    env.reset()

    result = env.step({"type": "wait", "args": {"minutes": 20}})

    assert result.success is True
    assert result.observation.current_time == "Day 1, 09:05"
    counter = next(item for item in result.observation.visible_objects if item.object_id == "counter")
    assert counter.visible_state == {"open": True, "snack_price": 1}


def test_dynamic_rule_can_combine_time_location_and_inventory_conditions(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.agent.inventory = {"apple": 1}
    state.objects["counter"].actionable = True
    state.objects["counter"].callable_actions = {
        "buy_snack": CallableActionDefinition(
            description="",
            arguments={},
            routes=[CallableActionRoute(match={}, effect=ObjectActionEffect(message="Bought a snack."))],
        ),
    }
    state.objects["counter"].visible_state = {"promo": False}
    state.dynamic_rules = [
        DynamicRule(
            rule_id="market_inventory_promo",
            when={
                "all": [
                    {"time_window": {"start": "09:00", "end": "10:00"}},
                    {"location_id": "market"},
                    {"has_inventory": {"apple": 1}},
                ]
            },
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"promo": True},
                    )
                }
            ),
        )
    ]

    active_view = build_effective_object_view(state, "counter", at_time=(9 * 60) + 5)
    assert active_view is not None
    assert active_view.object.visible_state == {"promo": True}

    state.agent.inventory = {}
    inactive_view = build_effective_object_view(state, "counter", at_time=(9 * 60) + 5)
    assert inactive_view is not None
    assert inactive_view.object.visible_state == {"promo": False}
