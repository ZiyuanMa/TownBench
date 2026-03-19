from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from engine.actions import Action, ActionExecution, apply_action_costs, get_action_spec, normalize_action
from engine.observation import Observation, project_observation, summarize_observation
from engine.results import StepResult
from engine.rules import apply_world_rules, evaluate_termination, merge_inventory_deltas
from engine.state import WorldState
from engine.trace import TraceEntry


@dataclass
class TransitionOutcome:
    state: WorldState
    result: StepResult
    trace_entry: TraceEntry


@dataclass
class StepEffects:
    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = field(default_factory=dict)
    triggered_events: list[str] = field(default_factory=list)


@dataclass
class StepSnapshot:
    observation: Observation
    done: bool
    termination_reason: str | None


class TransitionEngine:
    def step(
        self,
        state: WorldState,
        raw_action: Action | Mapping[str, Any],
        *,
        step_id: int,
    ) -> TransitionOutcome:
        raw_action_payload = _raw_action_payload(raw_action)
        working_state = state.model_copy(deep=True)
        try:
            action = normalize_action(raw_action)
        except ValidationError as exc:
            return self._build_invalid_action_outcome(
                state=working_state,
                raw_action_payload=raw_action_payload,
                step_id=step_id,
                warning=str(exc),
            )

        execution = self._execute_action(working_state, action)
        effects = self._apply_step_effects(working_state, action, execution)
        snapshot = self._snapshot_step(working_state, step_id=step_id)
        result = self._build_step_result(
            state=working_state,
            execution=execution,
            effects=effects,
            snapshot=snapshot,
        )
        trace_entry = self._build_trace_entry(
            action=action,
            execution=execution,
            effects=effects,
            snapshot=snapshot,
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

    def _apply_step_effects(
        self,
        state: WorldState,
        action: Action,
        execution: ActionExecution,
    ) -> StepEffects:
        effects = StepEffects(
            money_delta=execution.money_delta,
            energy_delta=execution.energy_delta,
            inventory_delta=dict(execution.inventory_delta or {}),
        )
        if not execution.success:
            return effects

        applied_cost = apply_action_costs(state, action.type)
        effects.time_delta = applied_cost.time_delta
        effects.money_delta += applied_cost.money_delta
        effects.energy_delta += applied_cost.energy_delta
        effects.inventory_delta = merge_inventory_deltas(effects.inventory_delta, applied_cost.inventory_delta)
        effects.triggered_events = apply_world_rules(state)
        return effects

    def _snapshot_step(self, state: WorldState, *, step_id: int) -> StepSnapshot:
        done, termination_reason = evaluate_termination(state, step_id=step_id)
        return StepSnapshot(
            observation=project_observation(state),
            done=done,
            termination_reason=termination_reason,
        )

    def _build_step_result(
        self,
        *,
        state: WorldState,
        execution: ActionExecution,
        effects: StepEffects,
        snapshot: StepSnapshot,
    ) -> StepResult:
        payload = execution.payload_builder(state) if execution.success and execution.payload_builder else {}
        return StepResult(
            success=execution.success,
            observation=snapshot.observation,
            message=execution.message,
            time_delta=effects.time_delta,
            money_delta=effects.money_delta,
            energy_delta=effects.energy_delta,
            inventory_delta=dict(effects.inventory_delta),
            triggered_events=list(effects.triggered_events),
            done=snapshot.done,
            termination_reason=snapshot.termination_reason,
            data=payload,
            warnings=[] if execution.success else [execution.error_type or "action_failed"],
        )

    def _build_trace_entry(
        self,
        *,
        action: Action,
        execution: ActionExecution,
        effects: StepEffects,
        snapshot: StepSnapshot,
        raw_action_payload: dict[str, Any],
        step_id: int,
    ) -> TraceEntry:
        return TraceEntry(
            step_id=step_id,
            raw_action=raw_action_payload,
            normalized_action=action.model_dump(),
            success=execution.success,
            error_type=execution.error_type,
            message=execution.message,
            time_delta=effects.time_delta,
            money_delta=effects.money_delta,
            energy_delta=effects.energy_delta,
            inventory_delta=dict(effects.inventory_delta),
            triggered_events=list(effects.triggered_events),
            observation_summary=summarize_observation(snapshot.observation),
            done=snapshot.done,
            termination_reason=snapshot.termination_reason,
        )

    def _build_invalid_action_outcome(
        self,
        *,
        state: WorldState,
        raw_action_payload: dict[str, Any],
        step_id: int,
        warning: str,
    ) -> TransitionOutcome:
        snapshot = self._snapshot_step(state, step_id=step_id)
        result = StepResult(
            success=False,
            observation=snapshot.observation,
            message="Invalid action payload.",
            done=snapshot.done,
            termination_reason=snapshot.termination_reason,
            warnings=[warning],
        )
        trace_entry = TraceEntry(
            step_id=step_id,
            raw_action=raw_action_payload,
            normalized_action={},
            success=False,
            error_type="invalid_action",
            message=result.message,
            observation_summary=summarize_observation(snapshot.observation),
            done=result.done,
            termination_reason=result.termination_reason,
        )
        return TransitionOutcome(state=state, result=result, trace_entry=trace_entry)


def _raw_action_payload(raw_action: Action | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw_action, Action):
        return raw_action.model_dump()
    return dict(raw_action)
