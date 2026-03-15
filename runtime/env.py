from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional, Union

from engine.actions import Action
from engine.observation import Observation, project_observation
from engine.results import StepResult
from engine.state import WorldState
from engine.trace import TraceEntry
from engine.transition import TransitionEngine


class TownBenchEnv:
    def __init__(self, initial_state: WorldState, engine: Optional[TransitionEngine] = None) -> None:
        self._initial_state = initial_state.model_copy(deep=True)
        self._engine = engine or TransitionEngine()
        self._state: Optional[WorldState] = None
        self._trace: list[TraceEntry] = []
        self._step_count = 0
        self._done = False
        self._termination_reason: Optional[str] = None

    @property
    def state(self) -> WorldState:
        if self._state is None:
            raise RuntimeError("Environment has not been reset.")
        return self._state

    def reset(self) -> Observation:
        self._state = self._initial_state.model_copy(deep=True)
        self._trace = []
        self._step_count = 0
        self._done = False
        self._termination_reason = None
        return project_observation(self._state)

    def step(self, action: Union[Action, Mapping[str, Any]]) -> StepResult:
        if self._state is None:
            self.reset()
        if self._done:
            return StepResult(
                success=False,
                observation=project_observation(self.state),
                message="Episode is already done.",
                done=True,
                termination_reason=self._termination_reason,
                warnings=["episode_done"],
            )

        outcome = self._engine.step(self.state, action, step_id=self._step_count + 1)
        self._state = outcome.state
        self._trace.append(outcome.trace_entry)
        self._step_count += 1
        self._done = outcome.result.done
        self._termination_reason = outcome.result.termination_reason
        return outcome.result

    def get_observation(self) -> Observation:
        return project_observation(self.state)

    def get_trace(self) -> list[TraceEntry]:
        return list(self._trace)

    def is_done(self) -> bool:
        return self._done
