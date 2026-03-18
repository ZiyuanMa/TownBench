from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from pydantic import ValidationError

from engine.actions import Action, normalize_action
from engine.observation import project_observation, summarize_observation
from engine.results import StepResult
from engine.rules import apply_action_costs, apply_world_rules, evaluate_termination, matches_world_flags
from engine.state import WorldObject, WorldState
from engine.trace import TraceEntry


@dataclass
class TransitionOutcome:
    state: WorldState
    result: StepResult
    trace_entry: TraceEntry


PayloadBuilder = Callable[[WorldState], dict[str, Any]]


@dataclass
class ActionExecution:
    success: bool
    message: str
    error_type: Optional[str] = None
    money_delta: int = 0
    payload_builder: Optional[PayloadBuilder] = None


ActionHandler = Callable[[WorldState, Action], ActionExecution]


class TransitionEngine:
    def step(
        self,
        state: WorldState,
        raw_action: Union[Action, Mapping[str, Any]],
        *,
        step_id: int,
    ) -> TransitionOutcome:
        raw_action_payload = _raw_action_payload(raw_action)
        working_state = state.model_copy(deep=True)
        try:
            action = normalize_action(raw_action)
        except ValidationError as exc:
            done, termination_reason = evaluate_termination(working_state, step_id=step_id)
            observation = project_observation(working_state)
            result = StepResult(
                success=False,
                observation=observation,
                message="Invalid action payload.",
                done=done,
                termination_reason=termination_reason,
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
                done=result.done,
                termination_reason=result.termination_reason,
            )
            return TransitionOutcome(state=working_state, result=result, trace_entry=trace_entry)

        time_delta = 0
        money_delta = 0
        energy_delta = 0
        inventory_delta: dict[str, int] = {}
        triggered_events: list[str] = []
        handler = ACTION_HANDLERS.get(action.type)
        if handler is None:
            execution = _failure("not_implemented", f"Action `{action.type}` is not implemented.")
        else:
            execution = handler(working_state, action)

        if execution.success:
            applied_cost = apply_action_costs(working_state, action.type)
            time_delta = applied_cost.time_delta
            money_delta = execution.money_delta + applied_cost.money_delta
            energy_delta = applied_cost.energy_delta
            inventory_delta = dict(applied_cost.inventory_delta)
            triggered_events = apply_world_rules(working_state)
        else:
            money_delta = execution.money_delta

        done, termination_reason = evaluate_termination(working_state, step_id=step_id)
        payload = execution.payload_builder(working_state) if execution.success and execution.payload_builder else {}

        observation = project_observation(working_state)
        result = StepResult(
            success=execution.success,
            observation=observation,
            message=execution.message,
            time_delta=time_delta,
            money_delta=money_delta,
            energy_delta=energy_delta,
            inventory_delta=inventory_delta,
            triggered_events=triggered_events,
            done=done,
            termination_reason=termination_reason,
            data=payload,
            warnings=[] if execution.success else [execution.error_type or "action_failed"],
        )
        trace_entry = TraceEntry(
            step_id=step_id,
            raw_action=raw_action_payload,
            normalized_action=action.model_dump(),
            success=execution.success,
            error_type=execution.error_type,
            message=execution.message,
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


def _success(
    message: str,
    *,
    payload_builder: Optional[PayloadBuilder] = None,
    money_delta: int = 0,
) -> ActionExecution:
    return ActionExecution(
        success=True,
        message=message,
        payload_builder=payload_builder,
        money_delta=money_delta,
    )


def _failure(error_type: str, message: str) -> ActionExecution:
    return ActionExecution(success=False, message=message, error_type=error_type)


def _handle_check_status(state: WorldState, action: Action) -> ActionExecution:
    del action
    return _success(
        "Status checked.",
        payload_builder=lambda current_state: {"agent_status": _serialize_agent_status(current_state)},
    )


def _handle_move_to(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "move_to requires a target_id.")

    current_location = state.locations[state.agent.location_id]
    if action.target_id not in state.locations:
        return _failure("unknown_location", f"Unknown location `{action.target_id}`.")
    if action.target_id not in current_location.links:
        return _failure("unreachable_location", f"Location `{action.target_id}` is not reachable.")

    state.agent.location_id = action.target_id
    target_location = state.locations[action.target_id]
    return _success(f"Moved to `{target_location.name}`.")


def _handle_inspect(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "inspect requires a target_id.")

    current_location = state.locations[state.agent.location_id]
    if action.target_id == current_location.location_id:
        return _success(
            f"Inspected location `{current_location.name}`.",
            payload_builder=lambda current_state, location_id=current_location.location_id: {
                "kind": "location",
                "location": current_state.locations[location_id].model_dump(),
            },
        )

    world_object = state.objects.get(action.target_id)
    if world_object is None:
        return _failure("unknown_target", f"Unknown inspect target `{action.target_id}`.")
    if world_object.location_id != current_location.location_id:
        return _failure("not_accessible", f"Target `{action.target_id}` is not in the current location.")
    if not world_object.inspectable:
        return _failure("not_inspectable", f"Target `{action.target_id}` cannot be inspected.")

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


def _handle_search(state: WorldState, action: Action) -> ActionExecution:
    del state, action
    return _failure("disabled_action", "search is intentionally disabled in the current milestone.")


def _handle_open_resource(state: WorldState, action: Action) -> ActionExecution:
    if not action.target_id:
        return _failure("missing_target", "open_resource requires a target_id.")

    current_location = state.locations[state.agent.location_id]
    world_object = state.objects.get(action.target_id)
    if world_object is None:
        return _failure("unknown_target", f"Unknown resource target `{action.target_id}`.")
    if world_object.location_id != current_location.location_id:
        return _failure("not_accessible", f"Target `{action.target_id}` is not in the current location.")
    if not world_object.readable or not world_object.resource_content:
        return _failure("not_readable", f"Target `{action.target_id}` is not a readable resource.")

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
        return _failure("missing_target", "load_skill requires a target_id.")

    skill = state.skills.get(action.target_id)
    if skill is None:
        return _failure("unknown_skill", f"Unknown skill `{action.target_id}`.")

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
        return _failure("missing_target", "call_action requires a target_id.")

    action_name = str(action.args.get("action", "")).strip()
    if not action_name:
        return _failure("missing_action_name", "call_action requires `args.action`.")

    current_location = state.locations[state.agent.location_id]
    world_object = state.objects.get(action.target_id)
    if world_object is None:
        return _failure("unknown_target", f"Unknown action target `{action.target_id}`.")
    if world_object.location_id != current_location.location_id:
        return _failure("not_accessible", f"Target `{action.target_id}` is not in the current location.")
    if not world_object.actionable:
        return _failure("not_actionable", f"Target `{action.target_id}` does not support actions.")
    if action_name not in world_object.action_ids:
        return _failure(
            "action_not_exposed",
            f"Action `{action_name}` is not exposed on `{action.target_id}` in the current location.",
        )

    effect = world_object.action_effects.get(action_name)
    if effect is None:
        return _failure(
            "unknown_object_action",
            f"Target `{action.target_id}` does not support `{action_name}`.",
        )
    if not matches_world_flags(state.world_flags, effect.required_world_flags):
        return _failure(
            "missing_prerequisites",
            f"Action `{action_name}` on `{action.target_id}` is not available in the current world state.",
        )

    world_object.visible_state.update(effect.set_visible_state)
    state.world_flags.update(effect.set_world_flags)
    if effect.money_delta:
        state.agent.money += effect.money_delta
    return _success(
        effect.message,
        payload_builder=lambda current_state, object_id=world_object.object_id, action_name=action_name: {
            "kind": "action",
            "object_id": object_id,
            "action": action_name,
            "visible_state": dict(current_state.objects[object_id].visible_state),
            "world_flags": dict(current_state.world_flags),
            "money": current_state.agent.money,
        },
        money_delta=effect.money_delta,
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


ACTION_HANDLERS: dict[str, ActionHandler] = {
    "check_status": _handle_check_status,
    "move_to": _handle_move_to,
    "inspect": _handle_inspect,
    "search": _handle_search,
    "open_resource": _handle_open_resource,
    "load_skill": _handle_load_skill,
    "write_note": _handle_write_note,
    "call_action": _handle_call_action,
}
