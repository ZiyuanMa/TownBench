# Area / Location Implementation Plan

## Goal

Implement the Area-enhanced location model proposed in [area_location_design_plan.md](./area_location_design_plan.md) with small, behavior-preserving steps.

The target is not a map-system rewrite. It is to add one semantic layer above `Location` so TownBench can model multi-room buildings while keeping:

- `Location` as the only navigable node
- object accessibility scoped to the current `Location`
- cross-area movement explicit and interpretable
- existing authored scenarios fully compatible

## Delivery Principles

This implementation should follow four rules throughout:

1. preserve existing scenario behavior before adding new semantics
2. make schema, loader, runtime, and observation changes in that order
3. add tests in the same phase as the behavior change
4. avoid introducing derived runtime state that can drift from source data

## Scope

### In Scope

- add `Area` to runtime state and scenario schema
- allow `Location` to optionally belong to one `Area`
- allow free movement within the same non-null `Area`
- expose `current_area` and `nearby_locations` in observations
- update baseline-facing move semantics description
- add one area-aware integration scenario

### Out Of Scope

- nested or multi-level areas
- `move_to(area_id)`
- `Area.links`
- area-level object access
- area-level event rules
- automatic area graph inference beyond same-area reachability

## Current Code Impact

The design affects five primary surfaces:

- `engine/state.py`: add runtime `Area`, extend `Location`, extend `WorldState`
- `scenario/schema.py`: add authored `areas` and `Location.area_id`
- `scenario/loader.py`: validate area references and build runtime state
- `engine/action_handlers.py`: adjust `move_to` reachability
- `engine/observation.py`: project area-aware observation fields

Secondary updates are expected in:

- `engine/actions.py`
- `baselines/openai_agents/tools.py`
- `tests/test_scenario_loader.py`
- `tests/test_transition.py`
- `tests/test_observation.py`
- `tests/conftest.py`
- `scenarios/multi_area_town/`
- `docs/architecture.md`

## Execution Plan

### Phase 1: Runtime State Foundation

### Objective

Make the runtime capable of representing areas without changing movement or observation behavior yet.

### Changes

- Add `Area` model to `engine/state.py`
- Add `area_id: str | None = None` to `Location`
- Add `areas: dict[str, Area] = Field(default_factory=dict)` to `WorldState`
- Keep `Area` normalized:
  - no `location_ids`
  - no adjacency data
  - no derived collections

### Tests

- add state model coverage in `tests/test_observation.py` or a new focused test module if that keeps concerns cleaner
- verify `Location.area_id` defaults to `None`
- verify `WorldState.areas` defaults to empty
- verify deep-copy / model serialization round-trips preserve `areas`

### Exit Criteria

- runtime state can hold areas without breaking existing fixtures or environment reset

### Phase 2: Scenario Schema And Loader

### Objective

Teach authored YAML to declare areas and validate them strictly.

### Changes

- Add `ScenarioAreaSource` to `scenario/schema.py`
- Add `areas: list[ScenarioAreaSource] = Field(default_factory=list)` to `ScenarioConfig`
- Extend `ScenarioLocationSource` with `area_id: str | None = None`
- Extend `ScenarioLocationSource.to_location()` to populate `area_id`
- In `scenario/loader.py`:
  - validate unique area ids
  - build runtime areas map
  - validate every non-null `Location.area_id` against known areas
  - pass `areas` into `_build_world_state`

### Tests

- parse authored YAML containing `areas`
- reject duplicate `area_id`
- reject location references to unknown `area_id`
- confirm old scenarios with no `areas` still load unchanged
- confirm authored `object_ids` rejection still works with `area_id` present

### Exit Criteria

- loader accepts both old flat scenarios and new area-aware scenarios

### Phase 3: Movement Semantics

### Objective

Add same-area implicit reachability while keeping all other navigation rules stable.

### Changes

- Update `_handle_move_to()` in `engine/action_handlers.py`
- Preserve validation order:
  1. missing target fails
  2. self-move succeeds as a no-op
  3. unknown target fails
  4. same non-null area succeeds
  5. explicit link succeeds
  6. otherwise fail as unreachable
- Do not change `move_to` input shape
- Do not change object action teleports via `move_to_location_id`

### Tests

- self-move returns success and leaves location unchanged
- same-area move without explicit link succeeds
- cross-area move with explicit link succeeds
- cross-area move without explicit link fails
- movement between locations with `area_id=None` still depends only on `links`
- object action teleports still ignore area reachability

### Exit Criteria

- reachable-set behavior matches the design matrix without breaking old movement tests

### Phase 4: Observation Projection

### Objective

Expose area context in a form that helps agents act without adding heavy map semantics.

### Changes

- Add `AreaObservation` to `engine/observation.py`
- Extend `Observation` with:
  - `current_area: AreaObservation | None = None`
  - `nearby_locations: list[str] = Field(default_factory=list)`
- Add helper for nearby-location expansion:
  - union of explicit `links`
  - plus all sibling locations in the same non-null area
  - excluding the current location
  - sorted for deterministic output
- Keep `current_location.links` as authored links only

### Tests

- `current_area` projects the correct area metadata
- `current_area` is `None` for locations without area assignment
- `nearby_locations` includes same-area implicit moves
- `nearby_locations` includes explicit cross-area links
- `nearby_locations` is deduplicated and sorted
- visible objects remain restricted to the current location only

### Exit Criteria

- observation exposes area semantics clearly without changing object visibility rules

### Phase 5: Baseline And Prompt Surface

### Objective

Align tool descriptions and public guidance with the new movement model.

### Changes

- Update `move_to` tool description in `engine/actions.py`
- Confirm `baselines/openai_agents/tools.py` reflects the updated description automatically
- Add recommended area guidance to the new scenario `public_rules`
- Avoid adding baseline-specific branching logic; observation changes should do most of the work

### Tests

- extend baseline tool-generation tests if needed to assert the new `move_to` description
- smoke-check that observation serialization includes `current_area` and `nearby_locations`

### Exit Criteria

- agents receive correct reachability guidance through both tools and observations

### Phase 6: Integration Scenario

### Objective

Add one town-centric scenario that uses areas for real authored value, not just schema coverage.

### Changes

- Add `scenarios/multi_area_town/scenario.yaml`
- Add minimal supporting `skills/` and `resources/` files only where they support the task loop
- Author an area-aware town layout centered on a phase2-style economy:
  - `market_block`
  - `workshop_building`
  - `service_hub`
  - `home_block`
  - `cafe_corner`
- Make at least one loop rely on:
  - multiple rooms inside one area
  - one explicit cross-area exit path
  - object interactions that still require exact room presence
- Prefer reusing the `phase2_town` economic loops and balance with map refactoring over inventing a fully new task system

### Tests

- add integration coverage similar to existing scenario tests
- verify internal room switching works without authored intra-area links
- verify cross-area travel still requires an entry/exit location
- verify task completion depends on being in the correct room, not merely the correct area

### Exit Criteria

- the new scenario demonstrates why `Area` exists and validates the authored ergonomics improvement

### Phase 7: Documentation Update

### Objective

Bring architecture docs in line with the shipped runtime behavior.

### Changes

- Update `docs/architecture.md`:
  - mention `areas` in `WorldState`
  - describe same-area movement semantics
  - describe the new observation fields
  - clarify that object accessibility remains location-scoped

### Exit Criteria

- architecture docs match code and scenario authoring behavior

## Test Strategy

The safest rollout order is:

1. update model defaults and fixtures
2. add schema parsing and loader validation
3. add movement tests before changing `move_to`
4. add observation tests before changing projection logic
5. add integration scenario last

Recommended command set during implementation:

```bash
.venv/bin/python -m pytest tests/test_scenario_loader.py
.venv/bin/python -m pytest tests/test_transition.py
.venv/bin/python -m pytest tests/test_observation.py
.venv/bin/python -m pytest tests/test_openai_baseline.py
.venv/bin/python -m pytest tests/test_phase1_scenario.py tests/test_phase2_scenario.py
```

Finish with:

```bash
.venv/bin/python -m pytest
```

## Compatibility Checks

The following invariants should stay true across the full rollout:

- existing scenarios load with zero YAML changes
- old flat locations still use explicit `links` only
- `current_location.links` does not silently gain implicit same-area links
- visible objects still come only from the exact current location
- object action teleport effects remain valid even when no navigable path exists
- failed `move_to` still applies no action cost
- successful self-move still applies the normal action cost

## Main Risks

### Risk 1: Silent Behavior Drift In Existing Scenarios

If old fixtures are updated carelessly, area-aware helper logic could leak into flat scenarios.

Mitigation:

- keep `area_id=None` as the default everywhere
- preserve old scenario fixtures in tests unchanged
- add explicit tests for the `None` / `None` reachability case

### Risk 2: Observation Confusion Between `links` And Reachability

Agents may misread `current_location.links` as the full move set after areas are introduced.

Mitigation:

- add `nearby_locations` rather than overloading `links`
- update tool descriptions and scenario `public_rules`
- keep output deterministic and simple

### Risk 3: Over-Expanding Phase 1 Scope

It is easy to let this work grow into a generalized map refactor.

Mitigation:

- do not add area-level links or movement during this implementation
- reject requirements that need nested containment or route planning
- keep `Area` as metadata plus same-area reachability only

## Recommended Delivery Order

If implemented in one branch, the smallest reviewable sequence is:

1. runtime state models
2. schema and loader validation
3. movement logic
4. observation projection
5. baseline wording updates
6. integration scenario
7. architecture documentation

If implemented across multiple PRs, split after Phase 2 and after Phase 4. That keeps each PR behaviorally coherent and testable.
