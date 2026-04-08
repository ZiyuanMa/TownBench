from engine.actions import ACTION_SPECS, TOOL_ACTION_SPECS, apply_action_costs, get_action_cost
from engine.state import ActionCost


def test_every_action_spec_has_a_handler():
    assert ACTION_SPECS
    assert all(spec.handler is not None for spec in ACTION_SPECS.values())


def test_tool_specs_are_backed_by_registered_actions():
    assert TOOL_ACTION_SPECS
    assert all(ACTION_SPECS[spec.action_type] is spec for spec in TOOL_ACTION_SPECS)


def test_move_to_tool_description_mentions_area_reachability():
    assert "same area" in ACTION_SPECS["move_to"].tool.description


def test_get_action_cost_prefers_runtime_override(minimal_world_state):
    minimal_world_state.action_costs["move_to"] = ActionCost(time_delta=3, energy_delta=-1, money_delta=2)

    cost = get_action_cost(minimal_world_state, "move_to")

    assert cost == ActionCost(time_delta=3, energy_delta=-1, money_delta=2)


def test_apply_action_costs_uses_shared_state_delta_logic(minimal_world_state):
    minimal_world_state.agent.inventory = {"apple": 1}
    minimal_world_state.action_costs["check_status"] = ActionCost(
        time_delta=2,
        money_delta=4,
        energy_delta=-5,
        inventory_delta={"apple": -1, "ticket": 1},
    )

    applied = apply_action_costs(minimal_world_state, "check_status")

    assert applied == ActionCost(
        time_delta=2,
        money_delta=4,
        energy_delta=-5,
        inventory_delta={"apple": -1, "ticket": 1},
    )
    assert minimal_world_state.current_time == 8 * 60 + 2
    assert minimal_world_state.agent.money == 24
    assert minimal_world_state.agent.energy == 95
    assert minimal_world_state.agent.inventory == {"ticket": 1}
