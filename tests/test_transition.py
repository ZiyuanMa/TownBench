from runtime.env import TownBenchEnv
from engine.state import ObjectActionEffect, WorldEventRule


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
    }


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
