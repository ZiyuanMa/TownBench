from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from engine.actions import Action, ActionExecution, apply_action_costs, get_action_cost, get_action_spec, normalize_action
from engine.observation import Observation, project_observation, summarize_observation
from engine.results import StepResult
from engine.rules import (
    apply_world_rules,
    evaluate_termination,
    merge_inventory_deltas,
    project_inventory,
    validate_inventory_delta,
)
from engine.state import ActionCost, WorldState
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
        original_state = state.model_copy(deep=True)
        working_state = state.model_copy(deep=True)
        try:
            action = normalize_action(raw_action)
        except ValidationError as exc:
            return self._build_invalid_action_outcome(
                state=original_state,
                raw_action_payload=raw_action_payload,
                step_id=step_id,
                warning=str(exc),
            )

        execution = self._execute_action(working_state, action)
        applied_state, execution, effects = self._apply_step_effects(
            original_state=original_state,
            working_state=working_state,
            action=action,
            execution=execution,
        )
        snapshot = self._snapshot_step(applied_state, step_id=step_id)
        result = self._build_step_result(
            state=applied_state,
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
        return TransitionOutcome(state=applied_state, result=result, trace_entry=trace_entry)

    def _execute_action(self, state: WorldState, action: Action) -> ActionExecution:
        spec = get_action_spec(action.type)
        if spec is None or spec.handler is None:
            return ActionExecution(
                success=False,
                message=f"Action `{action.type}` is not implemented.",
                error_type="not_implemented",
                result_data={"error_type": "not_implemented", "action_type": action.type},
            )
        return spec.handler(state, action)

    def _apply_step_effects(
        self,
        *,
        original_state: WorldState,
        working_state: WorldState,
        action: Action,
        execution: ActionExecution,
    ) -> tuple[WorldState, ActionExecution, StepEffects]:
        effects = StepEffects(
            money_delta=execution.money_delta,
            energy_delta=execution.energy_delta,
            inventory_delta=dict(execution.inventory_delta or {}),
        )
        if not execution.success:
            return original_state, execution, effects

        action_cost = get_action_cost(original_state, action.type)
        validation_error = self._validate_step_commit(
            state=original_state,
            execution=execution,
            action_cost=action_cost,
        )
        if validation_error is not None:
            return original_state, ActionExecution(
                success=False,
                message=validation_error[1],
                error_type=validation_error[0],
                result_data={"error_type": validation_error[0]},
            ), StepEffects()

        applied_cost = apply_action_costs(working_state, action.type)
        self._commit_validated_inventory(
            original_state=original_state,
            working_state=working_state,
            execution=execution,
            action_cost=applied_cost,
        )
        effects.time_delta = applied_cost.time_delta
        effects.money_delta += applied_cost.money_delta
        effects.energy_delta += applied_cost.energy_delta
        effects.inventory_delta = merge_inventory_deltas(effects.inventory_delta, applied_cost.inventory_delta)
        effects.triggered_events = apply_world_rules(working_state)
        return working_state, execution, effects

    def _validate_step_commit(
        self,
        *,
        state: WorldState,
        execution: ActionExecution,
        action_cost: ActionCost,
    ) -> tuple[str, str] | None:
        inventory_delta = merge_inventory_deltas(
            dict(execution.inventory_delta or {}),
            action_cost.inventory_delta,
        )
        inventory_error = validate_inventory_delta(
            state,
            inventory_delta,
            agent_stat_deltas=execution.agent_stat_deltas,
        )
        if inventory_error == "inventory_capacity_exceeded":
            return inventory_error, "Action would exceed the current carry limit."
        if inventory_error == "insufficient_inventory":
            return inventory_error, "Action would reduce inventory below zero."
        if state.agent.money + execution.money_delta + action_cost.money_delta < 0:
            return "insufficient_money", "Action would reduce money below zero."
        return None

    def _commit_validated_inventory(
        self,
        *,
        original_state: WorldState,
        working_state: WorldState,
        execution: ActionExecution,
        action_cost: ActionCost,
    ) -> None:
        inventory_delta = merge_inventory_deltas(
            dict(execution.inventory_delta or {}),
            action_cost.inventory_delta,
        )
        projected_inventory = project_inventory(original_state.agent.inventory, inventory_delta)
        if projected_inventory is None:
            raise RuntimeError("Validated inventory delta could not be committed.")
        working_state.agent.inventory = projected_inventory

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
        payload = dict(execution.result_data or {})
        if execution.payload_builder:
            payload.update(execution.payload_builder(state))
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
