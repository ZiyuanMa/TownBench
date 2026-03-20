from runtime.env import TownBenchEnv
from engine.state import ActionCost, ObjectActionEffect, WorldEventRule


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
        "notes": [],
        "status_effects": ["focused"],
        "stats": {"carry_limit": 3},
    }


def test_call_action_required_agent_stats_blocks_execution(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 2}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["lift_crate"]
    env.state.objects["counter"].action_effects = {
        "lift_crate": ObjectActionEffect(
            message="Lifted the crate.",
            required_agent_stats={"carry_limit": 3},
            set_visible_state={"crate_moved": True},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "lift_crate"}})

    assert result.success is False
    assert result.warnings == ["missing_prerequisites"]
    assert env.state.agent.stats == {"carry_limit": 2}
    assert env.state.objects["counter"].visible_state == {"open": True}


def test_call_action_agent_stat_deltas_update_state_and_payload(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 2}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["rent_cart"]
    env.state.objects["counter"].action_effects = {
        "rent_cart": ObjectActionEffect(
            message="Rented a hand cart.",
            money_delta=-4,
            required_money=4,
            agent_stat_deltas={"carry_limit": 3},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "rent_cart"}})

    assert result.success is True
    assert env.state.agent.stats == {"carry_limit": 5}
    assert result.data["stats"] == {"carry_limit": 5}


def test_call_action_can_reduce_carry_limit_to_zero_without_dropping_the_stat(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["disable_bag", "load_item"]
    env.state.objects["counter"].action_effects = {
        "disable_bag": ObjectActionEffect(
            message="Disabled the bag.",
            agent_stat_deltas={"carry_limit": -1},
        ),
        "load_item": ObjectActionEffect(
            message="Tried to load one item.",
            inventory_delta={"apple": 1},
        ),
    }
    env.step({"type": "move_to", "target_id": "market"})

    disabled = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "disable_bag"}})
    blocked = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "load_item"}})

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
    env.state.objects["counter"].action_ids = ["over_disable_bag", "check_zero_gate"]
    env.state.objects["counter"].action_effects = {
        "over_disable_bag": ObjectActionEffect(
            message="Over-disabled the bag.",
            agent_stat_deltas={"carry_limit": -2},
        ),
        "check_zero_gate": ObjectActionEffect(
            message="Zero-capacity gate passed.",
            required_agent_stats={"carry_limit": 0},
        ),
    }
    env.step({"type": "move_to", "target_id": "market"})

    disabled = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "over_disable_bag"}})
    gated = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "check_zero_gate"}})

    assert disabled.success is True
    assert env.state.agent.stats == {"carry_limit": 0}
    assert disabled.data["stats"] == {"carry_limit": 0}
    assert gated.success is True


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


def test_load_skill_returns_full_skill_payload(minimal_world_state):
    env = TownBenchEnv(minimal_world_state)
    env.reset()

    result = env.step({"type": "load_skill", "target_id": "safety_basics"})

    assert result.success is True
    assert result.data == {
        "kind": "skill",
        "skill_id": "safety_basics",
        "name": "Safety Basics",
        "description": "Simple safety reminders for acting in the town.",
        "content": "Always check your location before acting.",
    }


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


def test_call_action_can_apply_money_delta_and_reports_net_step_delta(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["sell_snack"]
    env.state.objects["counter"].action_effects = {
        "sell_snack": ObjectActionEffect(
            message="Sold a snack.",
            money_delta=7,
            set_visible_state={"last_sale": "snack"},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "args": {"action": "sell_snack"},
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
    env.state.objects["counter"].action_ids = ["buy_bulk"]
    env.state.objects["counter"].action_effects = {
        "buy_bulk": ObjectActionEffect(
            message="Bought a large bulk order.",
            inventory_delta={"apple": 6},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "buy_bulk"}})

    assert result.success is True
    assert env.state.agent.inventory == {"apple": 6}


def test_object_action_inventory_delta_respects_carry_limit(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["buy_bulk"]
    env.state.objects["counter"].action_effects = {
        "buy_bulk": ObjectActionEffect(
            message="Bought a large bulk order.",
            inventory_delta={"apple": 2},
            set_visible_state={"sale": "closed"},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "buy_bulk"}})

    assert result.success is False
    assert result.warnings == ["inventory_capacity_exceeded"]
    assert env.state.agent.inventory == {}
    assert env.state.objects["counter"].visible_state == {"open": True}


def test_object_action_can_increase_carry_limit_and_add_inventory_in_same_step(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["upgrade_and_load"]
    env.state.objects["counter"].action_effects = {
        "upgrade_and_load": ObjectActionEffect(
            message="Expanded the bag and loaded produce.",
            agent_stat_deltas={"carry_limit": 1},
            inventory_delta={"apple": 2},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "upgrade_and_load"}})

    assert result.success is True
    assert env.state.agent.stats == {"carry_limit": 2}
    assert env.state.agent.inventory == {"apple": 2}


def test_capacity_decrease_is_validated_against_projected_carry_limit(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 3}
    env.state.agent.inventory = {"apple": 2}
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["shrink_bag"]
    env.state.objects["counter"].action_effects = {
        "shrink_bag": ObjectActionEffect(
            message="Shrank the bag.",
            agent_stat_deltas={"carry_limit": -2},
            set_visible_state={"bag_size": "small"},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "shrink_bag"}})

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
    env.state.objects["counter"].action_ids = ["swap_item"]
    env.state.objects["counter"].action_effects = {
        "swap_item": ObjectActionEffect(
            message="Swapped the carried item.",
            inventory_delta={"banana": 1},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "swap_item"}})

    assert result.success is True
    assert result.inventory_delta == {"banana": 1, "apple": -1}
    assert env.state.agent.inventory == {"banana": 1}


def test_call_action_net_inventory_commit_uses_merged_delta_for_same_item(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.inventory = {"apple": 1}
    env.state.action_costs["call_action"] = ActionCost(inventory_delta={"apple": 1})
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["consume_and_rebate"]
    env.state.objects["counter"].action_effects = {
        "consume_and_rebate": ObjectActionEffect(
            message="Consumed apples with a rebate.",
            inventory_delta={"apple": -2},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "consume_and_rebate"}})

    assert result.success is True
    assert result.inventory_delta == {"apple": -1}
    assert env.state.agent.inventory == {}


def test_call_action_money_validation_uses_net_step_delta(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.money = 1
    env.state.action_costs["call_action"] = ActionCost(money_delta=2)
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["rebated_fee"]
    env.state.objects["counter"].action_effects = {
        "rebated_fee": ObjectActionEffect(
            message="Paid a fee with a matching rebate.",
            money_delta=-2,
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "rebated_fee"}})

    assert result.success is True
    assert result.money_delta == 0
    assert env.state.agent.money == 1


def test_combined_object_and_action_cost_inventory_delta_rolls_back_state(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.stats = {"carry_limit": 1}
    env.state.action_costs["call_action"] = ActionCost(inventory_delta={"bonus_ticket": 1})
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["buy_box"]
    env.state.objects["counter"].action_effects = {
        "buy_box": ObjectActionEffect(
            message="Bought one boxed order.",
            inventory_delta={"apple": 1},
            set_visible_state={"sale": "posted"},
            set_world_flags={"box_bought": True},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "buy_box"}})

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
    env.state.objects["counter"].action_ids = ["sell_snack"]
    env.state.objects["counter"].action_effects = {
        "sell_snack": ObjectActionEffect(
            message="Sold a snack.",
            set_visible_state={"sale": {"item": "snack", "history": ["snack"]}},
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step(
        {
            "type": "call_action",
            "target_id": "counter",
            "args": {"action": "sell_snack"},
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
    env.state.objects["counter"].action_ids = ["buy_ticket"]
    env.state.objects["counter"].action_effects = {
        "buy_ticket": ObjectActionEffect(
            message="Bought a return ticket.",
            required_money=6,
            money_delta=-6,
            energy_delta=5,
            inventory_delta={"ticket": 1},
            move_to_location_id="plaza",
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "buy_ticket"}})

    assert result.success is True
    assert result.money_delta == -6
    assert result.energy_delta == 2
    assert result.inventory_delta == {"ticket": 1}
    assert env.state.agent.location_id == "plaza"
    assert env.state.agent.money == 14
    assert env.state.agent.inventory == {"ticket": 1}
    assert result.data["location_id"] == "plaza"
    assert result.data["inventory"] == {"ticket": 1}


def test_call_action_rejects_when_required_inventory_is_missing(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["repair_device"]
    env.state.objects["counter"].action_effects = {
        "repair_device": ObjectActionEffect(
            message="Repaired device.",
            required_inventory={"repair_kit": 1},
            inventory_delta={"repair_kit": -1},
            money_delta=9,
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "repair_device"}})

    assert result.success is False
    assert result.warnings == ["missing_inventory"]
    assert env.state.agent.money == 20
    assert env.state.agent.inventory == {}


def test_call_action_rejects_when_money_would_drop_below_zero(minimal_world_state):
    env = TownBenchEnv(minimal_world_state.model_copy(deep=True))
    env.reset()
    env.state.agent.money = 4
    env.state.objects["counter"].actionable = True
    env.state.objects["counter"].action_ids = ["buy_machine"]
    env.state.objects["counter"].action_effects = {
        "buy_machine": ObjectActionEffect(
            message="Bought a machine.",
            required_money=5,
            money_delta=-5,
        )
    }
    env.step({"type": "move_to", "target_id": "market"})

    result = env.step({"type": "call_action", "target_id": "counter", "args": {"action": "buy_machine"}})

    assert result.success is False
    assert result.warnings == ["insufficient_money"]
    assert env.state.agent.money == 4
