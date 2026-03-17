from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional, Tuple, Union

from pydantic import ValidationError

from engine.actions import Action, normalize_action
from engine.observation import project_observation, summarize_observation
from engine.results import StepResult
from engine.rules import apply_action_costs, apply_world_rules, evaluate_termination
from engine.state import WorldObject, WorldState
from engine.trace import TraceEntry


@dataclass
class TransitionOutcome:
    state: WorldState
    result: StepResult
    trace_entry: TraceEntry


class TransitionEngine:
    def step(
        self,
        state: WorldState,
        raw_action: Union[Action, Mapping[str, Any]],
        *,
        step_id: int,
    ) -> TransitionOutcome:
        raw_action_payload = _raw_action_payload(raw_action)
        try:
            action = normalize_action(raw_action)
        except ValidationError as exc:
            observation = project_observation(state)
            result = StepResult(
                success=False,
                observation=observation,
                message="Invalid action payload.",
                warnings=[str(exc)],
            )
            trace_entry = TraceEntry(
                step_id=step_id,
                raw_action=raw_action_payload,
                normalized_action={},
                success=False,
                error_type="invalid_action",
                message=result.message,
                observation_summary=summarize_observation(observation),
            )
            return TransitionOutcome(state=state, result=result, trace_entry=trace_entry)

        working_state = state.model_copy(deep=True)
        success = True
        error_type: Optional[str] = None
        message = ""
        payload: dict[str, Any] = {}
        time_delta = 0
        money_delta = 0
        energy_delta = 0
        inventory_delta: dict[str, int] = {}
        triggered_events: list[str] = []

        if action.type == "check_status":
            payload["agent_status"] = _serialize_agent_status(working_state)
            message = "Status checked."
        elif action.type == "move_to":
            success, error_type, message = _handle_move_to(working_state, action)
        elif action.type == "inspect":
            success, error_type, message, payload = _handle_inspect(working_state, action)
        elif action.type == "search":
            success, error_type, message, payload = _handle_search(working_state, action)
        elif action.type == "open_resource":
            success, error_type, message, payload = _handle_open_resource(working_state, action)
        elif action.type == "load_skill":
            success, error_type, message, payload = _handle_load_skill(working_state, action)
        elif action.type == "write_note":
            success, error_type, message = _handle_write_note(working_state, action)
        elif action.type == "call_action":
            success, error_type, message, payload, effect_money_delta = _handle_call_action(working_state, action)
            money_delta += effect_money_delta
        else:
            success = False
            error_type = "not_implemented"
            message = f"Action `{action.type}` is not implemented in the current milestone."

        if success:
            applied_cost = apply_action_costs(working_state, action.type)
            time_delta = applied_cost.time_delta
            money_delta += applied_cost.money_delta
            energy_delta = applied_cost.energy_delta
            inventory_delta = dict(applied_cost.inventory_delta)
            triggered_events = apply_world_rules(working_state)

        done, termination_reason = evaluate_termination(working_state, step_id=step_id)

        observation = project_observation(working_state)
        result = StepResult(
            success=success,
            observation=observation,
            message=message,
            time_delta=time_delta,
            money_delta=money_delta,
            energy_delta=energy_delta,
            inventory_delta=inventory_delta,
            triggered_events=triggered_events,
            done=done,
            termination_reason=termination_reason,
            data=payload,
            warnings=[] if success else [error_type or "action_failed"],
        )
        trace_entry = TraceEntry(
            step_id=step_id,
            raw_action=raw_action_payload,
            normalized_action=action.model_dump(),
            success=success,
            error_type=error_type,
            message=message,
            time_delta=result.time_delta,
            money_delta=result.money_delta,
            energy_delta=result.energy_delta,
            inventory_delta=dict(result.inventory_delta),
            triggered_events=list(result.triggered_events),
            observation_summary=summarize_observation(observation),
            done=result.done,
            termination_reason=result.termination_reason,
        )
        return TransitionOutcome(state=working_state, result=result, trace_entry=trace_entry)


def _handle_move_to(state: WorldState, action: Action) -> Tuple[bool, Optional[str], str]:
    if not action.target_id:
        return False, "missing_target", "move_to requires a target_id."

    current_location = state.locations[state.agent.location_id]
    if action.target_id not in state.locations:
        return False, "unknown_location", f"Unknown location `{action.target_id}`."
    if action.target_id not in current_location.links:
        return False, "unreachable_location", f"Location `{action.target_id}` is not reachable."

    state.agent.location_id = action.target_id
    target_location = state.locations[action.target_id]
    return True, None, f"Moved to `{target_location.name}`."


def _handle_inspect(
    state: WorldState, action: Action
) -> Tuple[bool, Optional[str], str, dict[str, Any]]:
    if not action.target_id:
        return False, "missing_target", "inspect requires a target_id.", {}

    current_location = state.locations[state.agent.location_id]
    if action.target_id == current_location.location_id:
        return (
            True,
            None,
            f"Inspected location `{current_location.name}`.",
            {"kind": "location", "location": current_location.model_dump()},
        )

    world_object = state.objects.get(action.target_id)
    if world_object is None:
        return False, "unknown_target", f"Unknown inspect target `{action.target_id}`.", {}
    if world_object.location_id != current_location.location_id:
        return False, "not_accessible", f"Target `{action.target_id}` is not in the current location.", {}
    if not world_object.inspectable:
        return False, "not_inspectable", f"Target `{action.target_id}` cannot be inspected.", {}

    return (
        True,
        None,
        f"Inspected object `{world_object.name}`.",
        {"kind": "object", "object": _serialize_object(world_object)},
    )


def _handle_write_note(state: WorldState, action: Action) -> Tuple[bool, Optional[str], str]:
    text = str(action.args.get("text", "")).strip()
    if not text:
        return False, "missing_text", "write_note requires non-empty `args.text`.", ""

    state.agent.notes.append(text)
    return True, None, "Note saved."


def _handle_search(
    state: WorldState, action: Action
) -> Tuple[bool, Optional[str], str, dict[str, Any]]:
    return False, "disabled_action", "search is intentionally disabled in the current milestone.", {}


def _handle_open_resource(
    state: WorldState, action: Action
) -> Tuple[bool, Optional[str], str, dict[str, Any]]:
    if not action.target_id:
        return False, "missing_target", "open_resource requires a target_id.", {}

    current_location = state.locations[state.agent.location_id]
    world_object = state.objects.get(action.target_id)
    if world_object is None:
        return False, "unknown_target", f"Unknown resource target `{action.target_id}`.", {}
    if world_object.location_id != current_location.location_id:
        return False, "not_accessible", f"Target `{action.target_id}` is not in the current location.", {}
    if not world_object.readable or not world_object.resource_content:
        return False, "not_readable", f"Target `{action.target_id}` is not a readable resource.", {}

    return (
        True,
        None,
        f"Opened resource `{world_object.name}`.",
        {
            "kind": "resource",
            "object_id": world_object.object_id,
            "title": world_object.name,
            "content": world_object.resource_content,
        },
    )


def _handle_load_skill(
    state: WorldState, action: Action
) -> Tuple[bool, Optional[str], str, dict[str, Any]]:
    if not action.target_id:
        return False, "missing_target", "load_skill requires a target_id.", {}

    skill = state.skills.get(action.target_id)
    if skill is None:
        return False, "unknown_skill", f"Unknown skill `{action.target_id}`.", {}

    return (
        True,
        None,
        f"Loaded skill `{skill.name}`.",
        {
            "kind": "skill",
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "content": skill.content,
        },
    )


def _handle_call_action(
    state: WorldState, action: Action
) -> Tuple[bool, Optional[str], str, dict[str, Any], int]:
    if not action.target_id:
        return False, "missing_target", "call_action requires a target_id.", {}, 0

    action_name = str(action.args.get("action", "")).strip()
    if not action_name:
        return False, "missing_action_name", "call_action requires `args.action`.", {}, 0

    current_location = state.locations[state.agent.location_id]
    world_object = state.objects.get(action.target_id)
    if world_object is None:
        return False, "unknown_target", f"Unknown action target `{action.target_id}`.", {}, 0
    if world_object.location_id != current_location.location_id:
        return False, "not_accessible", f"Target `{action.target_id}` is not in the current location.", {}, 0
    if not world_object.actionable:
        return False, "not_actionable", f"Target `{action.target_id}` does not support actions.", {}, 0
    if action_name not in world_object.action_ids:
        return (
            False,
            "action_not_exposed",
            f"Action `{action_name}` is not exposed on `{action.target_id}` in the current location.",
            {},
            0,
        )

    effect = world_object.action_effects.get(action_name)
    if effect is None:
        return (
            False,
            "unknown_object_action",
            f"Target `{action.target_id}` does not support `{action_name}`.",
            {},
            0,
        )
    if not _matches_required_world_flags(state.world_flags, effect.required_world_flags):
        return (
            False,
            "missing_prerequisites",
            f"Action `{action_name}` on `{action.target_id}` is not available in the current world state.",
            {},
            0,
        )

    world_object.visible_state.update(effect.set_visible_state)
    state.world_flags.update(effect.set_world_flags)
    if effect.money_delta:
        state.agent.money += effect.money_delta
    return (
        True,
        None,
        effect.message,
        {
            "kind": "action",
            "object_id": world_object.object_id,
            "action": action_name,
            "visible_state": dict(world_object.visible_state),
            "world_flags": dict(state.world_flags),
            "money": state.agent.money,
        },
        effect.money_delta,
    )


def _serialize_object(world_object: WorldObject) -> dict[str, Any]:
    return {
        "object_id": world_object.object_id,
        "name": world_object.name,
        "object_type": world_object.object_type,
        "summary": world_object.summary,
        "visible_state": dict(world_object.visible_state),
        "action_ids": list(world_object.action_ids),
    }


def _serialize_agent_status(state: WorldState) -> dict[str, Any]:
    return {
        "current_time": state.current_time,
        "location_id": state.agent.location_id,
        "money": state.agent.money,
        "energy": state.agent.energy,
        "inventory": dict(state.agent.inventory),
        "notes": list(state.agent.notes),
        "status_effects": list(state.agent.status_effects),
    }


def _raw_action_payload(raw_action: Union[Action, Mapping[str, Any]]) -> dict[str, Any]:
    if isinstance(raw_action, Action):
        return raw_action.model_dump()
    return dict(raw_action)


def _matches_required_world_flags(current_flags: dict[str, bool], required_flags: dict[str, bool]) -> bool:
    return all(current_flags.get(flag) is expected for flag, expected in required_flags.items())
