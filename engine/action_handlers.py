from __future__ import annotations

from copy import deepcopy
from typing import Any

from engine.action_models import Action, ActionExecution, PayloadBuilder
from engine.rules import apply_state_delta, matches_world_flags
from engine.state import ActionCost, WorldObject, WorldState


def _success(
    message: str,
    *,
    result_data: dict[str, Any] | None = None,
    payload_builder: PayloadBuilder | None = None,
    money_delta: int = 0,
    energy_delta: int = 0,
    inventory_delta: dict[str, int] | None = None,
    agent_stat_deltas: dict[str, int] | None = None,
) -> ActionExecution:
    return ActionExecution(
        success=True,
        message=message,
        payload_builder=payload_builder,
        money_delta=money_delta,
        energy_delta=energy_delta,
        inventory_delta=dict(inventory_delta or {}),
        agent_stat_deltas=dict(agent_stat_deltas or {}),
        result_data=dict(result_data or {}),
    )


def _failure(error_type: str, message: str, *, result_data: dict[str, Any] | None = None) -> ActionExecution:
    payload = {"error_type": error_type}
    if result_data:
        payload.update(result_data)
    return ActionExecution(success=False, message=message, error_type=error_type, result_data=payload)


def _handle_check_status(state: WorldState, action: Action) -> ActionExecution:
    del action
    return _success(
        "Status checked.",
        payload_builder=lambda current_state: {"agent_status": _serialize_agent_status(current_state)},
    )


def _handle_move_to(state: WorldState, action: Action) -> ActionExecution:
    current_location = state.locations[state.agent.location_id]
    reachable_locations = _reachable_location_ids(state)
    if not action.target_id:
        return _failure(
            "missing_target",
            "move_to requires a target_id.",
            result_data={
                "current_location_id": current_location.location_id,
                "reachable_locations": reachable_locations,
            },
        )

    if action.target_id == current_location.location_id:
        return _success("You are already here.")

    target_location = state.locations.get(action.target_id)
    if target_location is None:
        return _failure(
            "unknown_location",
            f"Unknown location `{action.target_id}`.",
            result_data={
                "target_id": action.target_id,
                "current_location_id": current_location.location_id,
                "reachable_locations": reachable_locations,
            },
        )

    reachable = False
    if current_location.area_id is not None and current_location.area_id == target_location.area_id:
        reachable = True
    elif action.target_id in current_location.links:
        reachable = True

    if not reachable:
        return _failure(
            "unreachable_location",
            f"Location `{action.target_id}` is not reachable.",
            result_data={
                "target_id": action.target_id,
                "current_location_id": current_location.location_id,
                "reachable_locations": reachable_locations,
            },
        )

    state.agent.location_id = action.target_id
    return _success(f"Moved to `{target_location.name}`.")


def _handle_inspect(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure(
            "missing_target",
            "inspect requires a target_id.",
            result_data={"visible_object_ids": _visible_object_ids(state)},
        )

    current_location = state.locations[state.agent.location_id]
    if action.target_id == current_location.location_id:
        return _success(
            f"Inspected location `{current_location.name}`.",
            payload_builder=lambda current_state, location_id=current_location.location_id: {
                "kind": "location",
                "location": current_state.locations[location_id].model_dump(),
            },
        )

    world_object = _get_accessible_object(state, action.target_id)
    if isinstance(world_object, ActionExecution):
        return world_object
    if not world_object.inspectable:
        return _failure(
            "not_inspectable",
            f"Target `{action.target_id}` cannot be inspected.",
            result_data={
                "target_id": action.target_id,
                "visible_object_ids": _visible_object_ids(state),
            },
        )

    return _success(
        f"Inspected object `{world_object.name}`.",
        payload_builder=lambda current_state, object_id=world_object.object_id: {
            "kind": "object",
            "object": _serialize_object(current_state.objects[object_id]),
        },
    )


def _handle_write_note(state: WorldState, action: Action) -> ActionExecution:
    text = str(action.args.get("text", "")).strip()
    if not text:
        return _failure("missing_text", "write_note requires non-empty `args.text`.")

    state.agent.notes.append(text)
    return _success("Note saved.")


def _handle_open_resource(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure(
            "missing_target",
            "open_resource requires a target_id.",
            result_data={"visible_object_ids": _visible_object_ids(state)},
        )

    world_object = _get_accessible_object(state, action.target_id)
    if isinstance(world_object, ActionExecution):
        return world_object
    if not world_object.readable or not world_object.resource_content:
        return _failure(
            "not_readable",
            f"Target `{action.target_id}` is not a readable resource.",
            result_data={
                "target_id": action.target_id,
                "visible_object_ids": _visible_object_ids(state),
            },
        )

    return _success(
        f"Opened resource `{world_object.name}`.",
        payload_builder=lambda current_state, object_id=world_object.object_id: {
            "kind": "resource",
            "object_id": object_id,
            "title": current_state.objects[object_id].name,
            "content": current_state.objects[object_id].resource_content,
        },
    )


def _handle_load_skill(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure(
            "missing_target",
            "load_skill requires a target_id.",
            result_data={"visible_skill_ids": sorted(state.skills)},
        )

    skill = state.skills.get(action.target_id)
    if skill is None:
        return _failure(
            "unknown_skill",
            f"Unknown skill `{action.target_id}`.",
            result_data={
                "target_id": action.target_id,
                "visible_skill_ids": sorted(state.skills),
            },
        )

    return _success(
        f"Loaded skill `{skill.name}`.",
        payload_builder=lambda current_state, skill_id=skill.skill_id: {
            "kind": "skill",
            "skill_id": skill_id,
            "name": current_state.skills[skill_id].name,
            "description": current_state.skills[skill_id].description,
            "content": current_state.skills[skill_id].content,
        },
    )


def _handle_call_action(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure(
            "missing_target",
            "call_action requires a target_id.",
            result_data={"visible_object_ids": _visible_object_ids(state)},
        )

    action_name = str(action.args.get("action", "")).strip()
    if not action_name:
        return _failure(
            "missing_action_name",
            "call_action requires `args.action`.",
            result_data={
                "target_id": action.target_id,
                "visible_object_ids": _visible_object_ids(state),
            },
        )

    world_object = _get_accessible_object(state, action.target_id)
    if isinstance(world_object, ActionExecution):
        return world_object
    if not world_object.actionable:
        return _failure(
            "not_actionable",
            f"Target `{action.target_id}` does not support actions.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "available_actions": list(world_object.action_ids),
            },
        )
    if action_name not in world_object.action_ids:
        return _failure(
            "action_not_exposed",
            f"Action `{action_name}` is not exposed on `{action.target_id}` in the current location.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "available_actions": list(world_object.action_ids),
            },
        )

    effect = world_object.action_effects.get(action_name)
    if effect is None:
        return _failure(
            "unknown_object_action",
            f"Target `{action.target_id}` does not support `{action_name}`.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "available_actions": list(world_object.action_ids),
            },
        )
    if not matches_world_flags(state.world_flags, effect.required_world_flags):
        return _failure(
            "missing_prerequisites",
            f"Action `{action_name}` on `{action.target_id}` is not available in the current world state.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "required_world_flags": dict(effect.required_world_flags),
            },
        )
    if not _has_required_inventory(state, effect.required_inventory):
        return _failure(
            "missing_inventory",
            f"Action `{action_name}` on `{action.target_id}` requires inventory items that are not available.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "required_inventory": dict(effect.required_inventory),
                "current_inventory": dict(state.agent.inventory),
            },
        )
    if not _has_required_agent_stats(state, effect.required_agent_stats):
        return _failure(
            "missing_prerequisites",
            f"Action `{action_name}` on `{action.target_id}` requires agent stats that are not satisfied.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "required_agent_stats": dict(effect.required_agent_stats),
                "current_agent_stats": dict(state.agent.stats),
            },
        )
    if state.agent.money < effect.required_money:
        return _failure(
            "insufficient_money",
            f"Action `{action_name}` on `{action.target_id}` requires at least {effect.required_money} money.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "required_money": effect.required_money,
                "current_money": state.agent.money,
            },
        )
    if effect.move_to_location_id and effect.move_to_location_id not in state.locations:
        return _failure(
            "unknown_location",
            f"Action `{action_name}` on `{action.target_id}` references unknown location `{effect.move_to_location_id}`.",
            result_data={
                "target_id": action.target_id,
                "requested_action": action_name,
                "referenced_location_id": effect.move_to_location_id,
            },
        )

    world_object.visible_state.update(effect.set_visible_state)
    state.world_flags.update(effect.set_world_flags)
    _apply_agent_stat_deltas(state, effect.agent_stat_deltas)
    apply_state_delta(
        state,
        ActionCost(
            money_delta=effect.money_delta,
            energy_delta=effect.energy_delta,
            inventory_delta=effect.inventory_delta,
        ),
    )
    if effect.move_to_location_id:
        state.agent.location_id = effect.move_to_location_id
    return _success(
        effect.message,
        payload_builder=lambda current_state, object_id=world_object.object_id, action_name=action_name: {
            "kind": "action",
            "object_id": object_id,
            "action": action_name,
            "visible_state": deepcopy(current_state.objects[object_id].visible_state),
            "world_flags": dict(current_state.world_flags),
            "money": current_state.agent.money,
            "energy": current_state.agent.energy,
            "inventory": dict(current_state.agent.inventory),
            "stats": dict(current_state.agent.stats),
            "location_id": current_state.agent.location_id,
        },
        money_delta=effect.money_delta,
        energy_delta=effect.energy_delta,
        inventory_delta=effect.inventory_delta,
        agent_stat_deltas=effect.agent_stat_deltas,
    )


def _get_accessible_object(state: WorldState, target_id: str) -> WorldObject | ActionExecution:
    current_location = state.locations[state.agent.location_id]
    world_object = state.objects.get(target_id)
    if world_object is None:
        return _failure(
            "unknown_target",
            f"Unknown target `{target_id}`.",
            result_data={
                "target_id": target_id,
                "current_location_id": current_location.location_id,
                "visible_object_ids": _visible_object_ids(state),
            },
        )
    if world_object.location_id != current_location.location_id:
        return _failure(
            "not_accessible",
            f"Target `{target_id}` is not in the current location.",
            result_data={
                "target_id": target_id,
                "current_location_id": current_location.location_id,
                "visible_object_ids": _visible_object_ids(state),
            },
        )
    return world_object


def _serialize_object(world_object: WorldObject) -> dict[str, Any]:
    data = world_object.model_dump(
        include={"object_id", "name", "object_type", "summary", "visible_state", "action_ids"}
    )
    data["visible_state"] = deepcopy(world_object.visible_state)
    return data


def _serialize_agent_status(state: WorldState) -> dict[str, Any]:
    return {
        "current_time": state.current_time,
        **state.agent.model_dump(
            include={"location_id", "money", "energy", "inventory", "notes", "status_effects", "stats"}
        ),
    }


def _has_required_inventory(state: WorldState, required_inventory: dict[str, int]) -> bool:
    return all(state.agent.inventory.get(item_id, 0) >= required for item_id, required in required_inventory.items())


def _has_required_agent_stats(state: WorldState, required_agent_stats: dict[str, int]) -> bool:
    return all(state.agent.stats.get(stat_id, 0) >= required for stat_id, required in required_agent_stats.items())


def _apply_agent_stat_deltas(state: WorldState, agent_stat_deltas: dict[str, int]) -> None:
    for stat_id, delta in agent_stat_deltas.items():
        new_value = state.agent.stats.get(stat_id, 0) + delta
        if stat_id == "carry_limit":
            new_value = max(0, new_value)
        if new_value == 0 and stat_id != "carry_limit":
            state.agent.stats.pop(stat_id, None)
            continue
        state.agent.stats[stat_id] = new_value


def _visible_object_ids(state: WorldState) -> list[str]:
    current_location = state.locations[state.agent.location_id]
    return [object_id for object_id in current_location.object_ids if object_id in state.objects]


def _reachable_location_ids(state: WorldState) -> list[str]:
    current_location = state.locations[state.agent.location_id]
    nearby: set[str] = set(current_location.links)
    if current_location.area_id is not None:
        nearby.update(
            location.location_id
            for location in state.locations.values()
            if location.area_id == current_location.area_id
        )
    nearby.discard(current_location.location_id)
    return sorted(nearby)
