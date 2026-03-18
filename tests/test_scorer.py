from evaluation.scorer import score_episode
from engine.trace import TraceEntry


def test_score_episode_handles_empty_trace_as_non_terminal(minimal_world_state):
    score = score_episode([], minimal_world_state)

    assert score.done is False
    assert score.termination_reason is None
    assert score.step_count == 0
    assert score.summary.startswith("in_progress; termination=not_terminated;")


def test_score_episode_marks_success_from_termination_reason(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.world_flags["goal_met"] = True
    trace = [
        TraceEntry(
            step_id=1,
            raw_action={"type": "check_status"},
            normalized_action={"type": "check_status", "args": {}, "metadata": {}, "request_id": None, "target_id": None},
            success=True,
            message="Status checked.",
            done=True,
            termination_reason="success:goal_met",
            time_delta=0,
        )
    ]

    score = score_episode(trace, state)

    assert score.survived_days == 1
    assert score.final_money == 20
    assert score.done is True
    assert score.termination_reason == "success:goal_met"


def test_score_episode_keeps_non_terminal_trace_in_progress(minimal_world_state):
    trace = [
        TraceEntry(
            step_id=1,
            raw_action={"type": "move_to"},
            normalized_action={"type": "move_to"},
            success=True,
            message="Moved.",
            time_delta=10,
            done=False,
        )
    ]

    score = score_episode(trace, minimal_world_state)

    assert score.done is False
    assert score.termination_reason is None
    assert score.step_count == 1
    assert score.summary.startswith("in_progress; termination=not_terminated;")


def test_score_episode_uses_days_and_money_as_core_metrics(minimal_world_state):
    state = minimal_world_state.model_copy(deep=True)
    state.current_time = "Day 3, 09:00"
    state.agent.money = -4
    trace = [
        TraceEntry(
            step_id=1,
            raw_action={"type": "move_to"},
            normalized_action={"type": "move_to"},
            success=True,
            message="Moved.",
            time_delta=10,
        ),
        TraceEntry(
            step_id=2,
            raw_action={"type": "call_action"},
            normalized_action={"type": "call_action"},
            success=True,
            message="Done.",
            time_delta=5,
        ),
    ]

    score = score_episode(trace, state)

    assert score.survived_days == 3
    assert score.final_money == -4
    assert score.step_count == 2
