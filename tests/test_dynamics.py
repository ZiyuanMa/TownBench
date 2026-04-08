from engine.dynamics import build_effective_object_view, matches_time_window
from engine.rules import format_time_label, parse_time_label
from engine.state import (
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
    state.objects["counter"].action_ids = ["buy_snack", "buy_drink"]
    state.objects["counter"].visible_state = {"open": True, "snack_price": 3}
    state.objects["counter"].action_effects = {
        "buy_snack": ObjectActionEffect(message="Bought a snack.", required_money=3, money_delta=-3),
        "buy_drink": ObjectActionEffect(message="Bought a drink.", required_money=2, money_delta=-2),
    }
    state.dynamic_rules = [
        DynamicRule(
            rule_id="counter_closed_early",
            when=DynamicCondition(time_window=TimeWindow(start="17:00", end="08:30")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"open": False},
                        disabled_actions=["buy_snack"],
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
                        action_overrides={
                            "buy_snack": {
                                "required_money": 1,
                                "money_delta": -1,
                            }
                        },
                    )
                }
            ),
        ),
    ]

    early_view = build_effective_object_view(state, "counter", at_time=8 * 60)
    assert early_view is not None
    assert early_view.object.visible_state == {"open": False, "snack_price": 3}
    assert early_view.object.action_ids == ["buy_drink"]

    discount_view = build_effective_object_view(state, "counter", at_time=(9 * 60) + 15)
    assert discount_view is not None
    assert discount_view.object.visible_state == {"open": True, "snack_price": 1}
    assert discount_view.object.action_ids == ["buy_snack", "buy_drink"]
    assert discount_view.object.action_effects["buy_snack"].required_money == 1
    assert discount_view.object.action_effects["buy_snack"].money_delta == -1

    assert state.objects["counter"].visible_state == {"open": True, "snack_price": 3}
    assert state.objects["counter"].action_ids == ["buy_snack", "buy_drink"]
    assert state.objects["counter"].action_effects["buy_snack"].required_money == 3
    assert state.objects["counter"].action_effects["buy_snack"].money_delta == -3


def test_higher_priority_rule_can_reenable_action(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.agent.location_id = "market"
    state.objects["counter"].actionable = True
    state.objects["counter"].action_ids = ["buy_snack", "buy_drink"]
    state.objects["counter"].visible_state = {"open": True}
    state.objects["counter"].action_effects = {
        "buy_snack": ObjectActionEffect(message="Bought a snack."),
        "buy_drink": ObjectActionEffect(message="Bought a drink."),
    }
    state.dynamic_rules = [
        DynamicRule(
            rule_id="counter_closed",
            priority=0,
            when=DynamicCondition(time_window=TimeWindow(start="08:00", end="12:00")),
            apply=DynamicRuleApplication(
                object_overrides={
                    "counter": ObjectDynamicOverride(
                        visible_state={"open": False},
                        disabled_actions=["buy_snack", "buy_drink"],
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
                        enabled_actions=["buy_snack"],
                    )
                }
            ),
        ),
    ]

    closed_view = build_effective_object_view(state, "counter", at_time=(8 * 60) + 30)
    assert closed_view is not None
    assert closed_view.object.visible_state == {"open": False}
    assert closed_view.object.action_ids == []
    assert closed_view.disabled_actions == ("buy_drink", "buy_snack")

    reopened_view = build_effective_object_view(state, "counter", at_time=(9 * 60) + 15)
    assert reopened_view is not None
    assert reopened_view.object.visible_state == {"open": True, "special_window": True}
    assert reopened_view.object.action_ids == ["buy_snack"]
    assert reopened_view.disabled_actions == ("buy_drink",)
