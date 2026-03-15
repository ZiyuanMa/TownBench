from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from engine.rules import parse_time_label
from engine.state import WorldState
from engine.trace import TraceEntry


class EpisodeScore(BaseModel):
    survived_days: int
    final_money: int
    done: bool
    termination_reason: Optional[str] = None
    step_count: int
    summary: str


def score_episode(trace: list[TraceEntry], final_state: WorldState) -> EpisodeScore:
    step_count = len(trace)
    last_entry = trace[-1] if trace else None
    done = bool(last_entry.done) if last_entry else False
    termination_reason = last_entry.termination_reason if last_entry else None
    survived_days = _extract_survived_days(final_state.current_time)
    final_money = final_state.agent.money

    return EpisodeScore(
        survived_days=survived_days,
        final_money=final_money,
        done=done,
        termination_reason=termination_reason,
        step_count=step_count,
        summary=_build_summary(
            survived_days=survived_days,
            final_money=final_money,
            done=done,
            termination_reason=termination_reason,
            step_count=step_count,
        ),
    )


def _extract_survived_days(current_time: str) -> int:
    total_minutes = parse_time_label(current_time)
    return total_minutes // (24 * 60) + 1


def _build_summary(
    *,
    survived_days: int,
    final_money: int,
    done: bool,
    termination_reason: Optional[str],
    step_count: int,
) -> str:
    status = "finished" if done else "in_progress"
    termination = termination_reason or "not_terminated"
    return (
        f"{status}; termination={termination}; survived_days={survived_days}; "
        f"final_money={final_money}; steps={step_count}"
    )
