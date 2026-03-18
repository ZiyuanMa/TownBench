from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Union

from pydantic import ValidationError

from engine.actions import Action, ActionExecution, apply_action_costs, get_action_spec, normalize_action
from engine.observation import project_observation, summarize_observation
from engine.results import StepResult
from engine.rules import apply_world_rules, evaluate_termination, merge_inventory_deltas
from engine.state import WorldState
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
        working_state = state.model_copy(deep=True)
        try:
            action = normalize_action(raw_action)
        except ValidationError as exc:
            return _build_invalid_action_outcome(
                state=working_state,
                raw_action_payload=raw_action_payload,
                step_id=step_id,
                warning=str(exc),
            )

        execution = self._execute_action(working_state, action)
        result, trace_entry = _build_step_artifacts(
            state=working_state,
            action=action,
            execution=execution,
            raw_action_payload=raw_action_payload,
            step_id=step_id,
        )
        return TransitionOutcome(state=working_state, result=result, trace_entry=trace_entry)

    def _execute_action(self, state: WorldState, action: Action) -> ActionExecution:
        spec = get_action_spec(action.type)
        if spec is None or spec.handler is None:
            return ActionExecution(
                success=False,
                message=f"Action `{action.type}` is not implemented.",
                error_type="not_implemented",
            )
        return spec.handler(state, action)


def _build_invalid_action_outcome(
    *,
    state: WorldState,
    raw_action_payload: dict[str, Any],
    step_id: int,
    warning: str,
) -> TransitionOutcome:
    done, termination_reason = evaluate_termination(state, step_id=step_id)
    observation = project_observation(state)
    result = StepResult(
        success=False,
        observation=observation,
        message="Invalid action payload.",
        done=done,
        termination_reason=termination_reason,
        warnings=[warning],
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
    return TransitionOutcome(state=state, result=result, trace_entry=trace_entry)


def _build_step_artifacts(
    *,
    state: WorldState,
    action: Action,
    execution: ActionExecution,
    raw_action_payload: dict[str, Any],
    step_id: int,
) -> tuple[StepResult, TraceEntry]:
    time_delta = 0
    money_delta = execution.money_delta
    energy_delta = execution.energy_delta
    inventory_delta = dict(execution.inventory_delta or {})
    triggered_events: list[str] = []

    if execution.success:
        applied_cost = apply_action_costs(state, action.type)
        time_delta = applied_cost.time_delta
        money_delta += applied_cost.money_delta
        energy_delta += applied_cost.energy_delta
        inventory_delta = merge_inventory_deltas(inventory_delta, applied_cost.inventory_delta)
        triggered_events = apply_world_rules(state)

    done, termination_reason = evaluate_termination(state, step_id=step_id)
    payload = execution.payload_builder(state) if execution.success and execution.payload_builder else {}
    observation = project_observation(state)
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
    return result, trace_entry


def _raw_action_payload(raw_action: Union[Action, Mapping[str, Any]]) -> dict[str, Any]:
    if isinstance(raw_action, Action):
        return raw_action.model_dump()
    return dict(raw_action)
