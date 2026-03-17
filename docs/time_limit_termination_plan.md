# Time-Limit Termination Plan

## Why

TownBench already models in-world time through `current_time` and per-action `time_delta`, but episode termination is still centered on `max_steps`.

That creates two problems:

- `max_steps` does not match the benchmark's actual resource model. The environment already tracks time directly.
- Baseline-side runner limits such as `max_turns` are easy to confuse with environment limits, even though they count different things.

The benchmark should primarily stop because in-world time has run out, not because an arbitrary number of actions was reached.

## Goal

Move the benchmark's main episode budget from action count to environment time.

The intended user-facing model is:

- scenarios define how much in-world time an episode lasts
- each action spends in-world time
- the environment ends when that time budget is exhausted

## Proposed Model

Add a time-based termination field to `TerminationConfig`.

Preferred option:

- `max_time_minutes: Optional[int] = None`

Meaning:

- this is the total elapsed in-world time allowed from the scenario's starting `current_time`
- when elapsed time is greater than or equal to `max_time_minutes`, the episode ends with a time-limit termination reason

Example:

- scenario starts at `Day 1, 08:00`
- `max_time_minutes = 90`
- episode ends once simulated time reaches or passes `Day 1, 09:30`

## Termination Semantics

Termination priority should remain explicit and deterministic.

Suggested order inside `evaluate_termination(...)`:

1. success world flags
2. failure world flags
3. zero energy
4. time limit reached
5. optional internal safety caps

Suggested termination reason:

- `time_limit_reached`

## Schema Changes

Update `engine/state.py`:

- add `max_time_minutes: Optional[int] = None` to `TerminationConfig`

Scenario authoring:

- scenarios should prefer `max_time_minutes`
- `max_steps` should be treated as deprecated benchmark budget

## Engine Changes

Update `engine/rules.py`:

- compute elapsed minutes as `parse_time_label(state.current_time) - parse_time_label(initial_time)`
- terminate when elapsed minutes is greater than or equal to `max_time_minutes`

This requires the environment to retain the scenario's initial time in a stable way.

Two reasonable implementations:

1. add `start_time: str` to `WorldState` when loading the scenario
2. store the initial parsed minute count in state metadata or stats

Option 1 is clearer and easier to test.

## Baseline and Runner Implications

`max_turns` should not define benchmark semantics.

Recommended direction:

- scenario time limit controls environment termination
- OpenAI runner `max_turns` becomes an internal safety cap only
- do not map scenario budgets directly onto SDK `max_turns`

That preserves a clean separation:

- environment budget = in-world time
- runner budget = implementation safety guard

## Migration Plan

Phase 1:

- add `max_time_minutes`
- keep `max_steps` working for backward compatibility
- prefer time-based termination in new scenarios

Phase 2:

- update `demo_town` to use a time budget
- update tests to assert `time_limit_reached`
- stop treating `max_steps` as the primary benchmark budget

Phase 3:

- deprecate `max_steps` in scenario docs
- keep only a non-user-facing internal safety cap where needed

## Testing Plan

Add focused tests for:

- episode ends exactly when elapsed time reaches the configured limit
- episode does not end early when elapsed time is still below the limit
- crossing midnight or multiple days still computes elapsed time correctly
- zero-energy termination still works independently of time termination
- success and failure flags still take precedence if that ordering is chosen

## Open Questions

- Whether `max_steps` should remain available as a hidden safety mechanism or be removed entirely later
- Whether scenarios should support `end_time` in addition to `max_time_minutes`
- Whether scorer summaries should explicitly report elapsed minutes
