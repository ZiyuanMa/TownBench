# Architecture Refactor Plan

## Goal

Refactor TownBench in small, behavior-preserving steps so the codebase is easier to extend, test, and reason about.

The immediate target is not to redesign the benchmark. It is to reduce avoidable coupling in:

- action registration
- transition execution
- scenario authoring and loading
- baseline orchestration

This plan assumes existing benchmark behavior should remain stable during the refactor. `demo_town` and `phase1_town` should keep the same authored semantics, and the current test suite should stay green throughout.

## Current Assessment

TownBench already has a workable top-level architecture:

- `scenario/` parses authored YAML and asset files into runtime state
- `engine/` owns state transition, rules, observation projection, and trace generation
- `runtime/` wraps the engine as an episode environment
- `baselines/` adapts the environment to agent SDKs
- `evaluation/` computes post-episode metrics

This structure is sound. The problem is inside the boundaries:

- action definitions are split across multiple modules
- `TransitionEngine` owns too many responsibilities
- runtime state and scenario authoring models are only partially separated
- baseline orchestration is still provider-specific and concentrated in one runner

These issues do not currently break the benchmark, but they will slow down future work such as:

- adding new action types
- adding more complex event and resource mechanics
- growing the number of scenarios
- supporting more than one baseline provider

## Refactor Principles

All four phases should follow the same rules:

1. preserve behavior before improving elegance
2. keep changes incremental and reviewable
3. make one module the single source of truth for each concept
4. prefer explicit builders and processors over mixed responsibilities
5. add direct tests where logic becomes more modular

## Phase 1: Consolidate Action Registry And Effect Application

### Why

Today, the action system is split across:

- action type and tool metadata in `engine/actions.py`
- default cost lookup in `engine/rules.py`
- action handler dispatch in `engine/transition.py`

This makes action evolution error-prone. Adding one new action requires coordinated edits across multiple files.

Resource mutation logic is also duplicated between generic action costs and object action effects. That duplication increases the risk of semantic drift for money, energy, inventory, and location updates.

### Scope

This phase should make action definition and action execution setup more coherent without changing external behavior.

### Proposed Changes

- Extend `ActionSpec` so it can hold:
  - `action_type`
  - `default_cost`
  - `tool`
  - `handler`
- Remove the separate `ACTION_HANDLERS` registry from `engine/transition.py`.
- Resolve handlers from the action registry instead of maintaining a second mapping.
- Extract shared resource and inventory mutation helpers so both:
  - default action costs
  - object action effects
  use the same mutation path.
- Keep `Action`, `ActionToolSpec`, and baseline tool generation behavior stable.

### Likely Files

- `engine/actions.py`
- `engine/rules.py`
- `engine/transition.py`
- `tests/test_transition.py`
- new focused rule or registry tests

### Acceptance Criteria

- adding a new action requires editing one registry definition, not multiple disconnected maps
- default costs and handlers stay aligned by construction
- money, energy, and inventory updates are applied through one shared implementation path
- all existing transition and baseline tests still pass

### Risks

- circular imports if handlers are attached to specs carelessly
- accidental behavior drift in step delta reporting

### Mitigation

- keep handler definitions in one module during the first pass, but derive dispatch from the central registry
- add direct tests for resource delta behavior before removing duplication

## Phase 2: Decompose The Transition Pipeline

### Why

`TransitionEngine.step()` currently handles:

- action normalization
- execution dispatch
- domain mutation
- cost application
- world event triggering
- termination evaluation
- observation construction
- trace construction

That makes `engine/transition.py` the heaviest coordination point in the codebase.

### Scope

This phase should keep the same episode semantics while breaking the transition path into explicit sub-steps.

### Proposed Changes

- Split `TransitionEngine.step()` into internal phases such as:
  - normalize action
  - execute action
  - apply post-action costs and effects
  - apply world events
  - evaluate termination
  - build `StepResult`
  - build `TraceEntry`
- Extract shared target-resolution helpers for:
  - current location lookup
  - accessible object lookup
  - readable object lookup
  - actionable object lookup
- Move event evaluation into a dedicated event processor so event logic is no longer mixed with time and termination helpers.
- Keep `TownBenchEnv` thin and unchanged in public API.

### Likely Files

- `engine/transition.py`
- `engine/rules.py`
- possible new helper module under `engine/`
- `tests/test_transition.py`
- new direct tests for event processing and target resolution

### Acceptance Criteria

- `TransitionEngine.step()` becomes a short orchestration method instead of a monolithic implementation
- event processing can be tested in isolation
- repeated accessibility validation logic is removed from individual handlers
- step result and trace payloads remain backward compatible

### Risks

- regressions in error typing or warning payloads
- subtle ordering changes between cost application, event triggering, and termination

### Mitigation

- preserve current ordering explicitly in tests
- add focused tests for invalid actions, non-once events, and success/failure termination precedence

## Phase 3: Clean Up Scenario Schema And Loader

### Why

The scenario pipeline currently mixes authoring-only models with direct reuse of runtime models. This creates an inconsistent contract:

- some authored sections are strict and clearly validated
- some nested sections reuse runtime models and may silently accept extra fields

The loader also combines parsing, validation, asset resolution, and runtime assembly in one function.

### Scope

This phase should make authoring validation more explicit and make the loading pipeline easier to extend.

### Proposed Changes

- Choose a clearer boundary for scenario authoring models:
  - either fully authored DTOs in `scenario/schema.py`
  - or consistent runtime model reuse with explicit wrappers only where needed
- Apply strict validation consistently to authored sections, including:
  - initial agent state
  - action costs
  - event rules
  - termination config
- Split `load_scenario()` into explicit stages:
  - parse config
  - validate references
  - resolve external assets
  - build runtime `WorldState`
- Make `resource_file` and `resource_content` mutually exclusive.
- Revisit whether `actionable` should remain authored or be derived from `action_effects`.
- Keep scenario YAML compatibility where possible during the first refactor pass.

### Likely Files

- `scenario/schema.py`
- `scenario/loader.py`
- `engine/state.py`
- `tests/test_scenario_loader.py`
- `tests/test_phase1_scenario.py`

### Acceptance Criteria

- authoring validation rules are consistent across the full scenario schema
- loader responsibilities are split into small, testable units
- asset-loading behavior is explicit and unambiguous
- existing scenarios load without behavior changes

### Risks

- over-normalizing the schema and making authored content harder to write
- breaking scenario compatibility while trying to improve validation

### Mitigation

- keep author-facing YAML stable unless there is a strong correctness reason to change it
- preserve current scenarios as integration fixtures throughout the refactor

## Phase 4: Extract Provider-Agnostic Baseline Core

### Why

The current OpenAI baseline works, but most orchestration lives in one provider-specific runner. That is manageable with one provider, but it will become awkward if TownBench adds:

- additional baseline implementations
- more CLI entrypoints
- richer streaming or tracing hooks

The current baseline package also has a weak abstraction center: `baselines/base.py` mostly defines a result DTO, not a reusable baseline execution contract.

### Scope

This phase should separate generic episode orchestration from OpenAI SDK adaptation.

### Proposed Changes

- Extract provider-agnostic episode preparation and result-building logic into a reusable baseline core.
- Leave provider-specific responsibilities to the OpenAI layer, such as:
  - agent construction
  - SDK runner calls
  - stream event translation
- Isolate prompt construction from the runner.
- Reduce duplicate sync and streamed completion logic.
- Replace passive container classes with dataclasses where appropriate.
- Revisit whether global SDK mutation such as default API selection should remain process-wide.

### Likely Files

- `baselines/base.py`
- `baselines/openai_agents/agent.py`
- `baselines/openai_agents/config.py`
- `baselines/openai_agents/runner.py`
- `baselines/openai_agents/tools.py`
- `scripts/run_openai_baseline.py`
- `evaluation/scorer.py`
- `tests/test_openai_baseline.py`
- `tests/test_scorer.py`

### Acceptance Criteria

- baseline orchestration logic is reusable across providers
- prompt construction is isolated from runner control flow
- sync and streamed execution share a common completion path
- missing optional dependencies fail cleanly and predictably

### Risks

- introducing abstraction too early for code that still only has one provider
- making the OpenAI baseline harder to read in the name of generality

### Mitigation

- keep the extracted core small and concrete
- only abstract code that is already duplicated or clearly provider-neutral

## Recommended Order

The recommended execution order is:

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4

That order keeps the highest-value internal cleanup first:

- action consistency first
- transition simplification second
- authoring and loader cleanup third
- multi-provider baseline cleanup last

## Testing Strategy

The refactor should be guarded by both existing tests and a few new direct unit tests.

Existing suites that should remain green throughout:

- `tests/test_transition.py`
- `tests/test_env.py`
- `tests/test_observation.py`
- `tests/test_trace.py`
- `tests/test_scenario_loader.py`
- `tests/test_phase1_scenario.py`
- `tests/test_openai_baseline.py`
- `tests/test_scorer.py`

Recommended additions during the refactor:

- direct tests for action registry consistency
- direct tests for shared resource delta application
- direct tests for event processor behavior
- direct tests for loader sub-steps
- direct tests for scorer behavior on empty and non-terminal traces

## Non-Goals

This plan does not aim to:

- redesign benchmark economics
- replace the current scenario format with a new DSL
- remove Pydantic from the codebase
- introduce advanced simulation mechanics during the refactor itself

Those are separate decisions. This document is only about reducing structural complexity in the existing architecture.

## Definition Of Done

The architecture refactor is complete when:

- the action system has a single authoritative registry
- transition execution is decomposed into small testable units
- scenario authoring and loading have clearer boundaries
- baseline orchestration has a small provider-agnostic core
- the benchmark behavior of existing scenarios remains stable
- the full test suite stays green during and after the transition
