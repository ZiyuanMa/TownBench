# Dynamic Mechanisms Design

## Goal

This document describes how to introduce dynamic mechanisms into TownBench so that
the environment changes over time in ways that materially affect agent planning.

The immediate target is a deterministic Phase 3 upgrade centered on three
mechanisms:

- business hours
- price windows
- short-lived high-value windows

The design goal is not to make the world noisy for its own sake. The goal is to
make the same action sequence produce different value at different times, so the
agent must schedule, reprioritize, and react to opportunity cost.

## Design Principles

- Dynamics must be visible to the agent through observation, not only encoded in
  hidden logic.
- Dynamics must affect real execution, not only object descriptions.
- The first version should be deterministic and seed-stable.
- Static authored content should remain the base layer; dynamic logic should be
  an overlay evaluated at runtime.
- The environment should continue to be debuggable from traces and explicit
  current state.

## Why The Current Model Is Not Enough

Today TownBench already tracks authored time labels and static event rules, but
its main interaction model is still effectively static:

- `current_time` is primarily a display label advanced by action costs.
- `event_rules` are driven by `world_flags`, which works well for authored state
  machines and notices.
- object action behavior is authored statically in `action_effects`.

This is enough for linear or loop-based scenarios, but it is not enough for:

- a shop that is visible but closed right now
- a buyer whose payout changes by time of day
- a short profit spike that should temporarily dominate the normal plan

If these behaviors are expressed only through `world_flags`, authored scenarios
become brittle and difficult to maintain. If they are expressed only through
`visible_state`, the observation can drift away from real execution.

## How Dynamics Should Appear In The Environment

Dynamic mechanisms should be expressed in three layers at the same time.

### 1. Public Signal Layer

The agent should be able to observe the dynamic state through normal environment
channels:

- `current_time`
- object `visible_state`
- readable boards, notices, and ledgers
- available or unavailable actions

Examples:

- `coffee_counter.visible_state.open = false`
- `goods_buyer.visible_state.packed_tea_payout = 16`
- `operations_board` announces that a lunch rush is active until 12:30

This ensures the benchmark measures adaptation to observed conditions rather than
guessing hidden simulator rules.

### 2. Execution Layer

The same dynamic state must affect the actual transition logic:

- closed shops reject actions
- active windows change payout or cost
- temporary opportunities modify the action the agent should prefer

The key invariant is:

- displayed price or availability must match the price or availability used by
  `call_action`

### 3. Opportunity-Cost Layer

The dynamic must be strong enough to alter the best plan.

Examples:

- a meal box is usually a low-margin fallback, but becomes the best cash loop
  during a short lunch rush
- a repair payout is strong, but only if the service depot is open when the
  ticket is ready
- a tea buyer pays more in an afternoon shortage window, so the agent may want
  to pre-produce inventory and wait

If a dynamic does not change ordering, timing, or route choice, it is flavor
text rather than benchmark difficulty.

## Recommended Runtime Model

The recommended implementation is a runtime overlay layer evaluated from the
current time before action execution and again after time advances.

### Base Layer

The authored scenario remains the source of truth for:

- locations
- objects
- base `visible_state`
- base `action_effects`
- static event rules

### Dynamic Overlay Layer

At runtime, the engine computes an effective view of the current world:

- effective object visibility and metadata
- effective action availability
- effective action effect values such as payout or cost

This computed view should not permanently mutate the base authored data. It
should be resolved from the current state plus active dynamic rules.

This keeps scenario content readable and avoids permanent drift from repeated
time-based toggles.

## Scope Of Phase 3 MVP

The first implementation should support only deterministic time-window dynamics.

Included:

- business hours
- price windows
- short-lived high-value windows

Deferred:

- stochastic market movement
- random job spawning
- cross-object supply simulation
- hidden dynamic rules that the agent cannot observe
- complex capacity auctions or reservation systems

This is enough to make planning time-sensitive without making evaluation hard to
interpret.

## Proposed Schema

The simplest scalable schema is a list of dynamic rules separate from
`event_rules`.

Suggested top-level addition to scenario YAML:

```yaml
dynamic_rules:
  - rule_id: breakfast_bonus
    priority: 100
    when:
      time_window:
        start: "06:00"
        end: "10:00"
    apply:
      object_overrides:
        meal_counter:
          visible_state:
            meal_box_payout: 8
          action_overrides:
            sell_meal_box:
              money_delta: 8
```

### Why Separate From `event_rules`

`event_rules` are already a good fit for state-triggered authored transitions,
especially those driven by `world_flags`.

Dynamic mechanisms are different:

- they are evaluated continuously from time
- they often need priorities and override semantics
- they often change both observation and execution
- they should be composable without encoding large flag state machines

For that reason, `dynamic_rules` should remain a dedicated concept.

## Proposed Data Model

The exact implementation can vary, but the recommended model is:

- `TimeWindow`
  - `start`
  - `end`
- `DynamicCondition`
  - initially just `time_window`
  - optionally later combine with flags or agent location
- `ActionEffectOverride`
  - partial overrides for authored `ObjectActionEffect`
- `ObjectOverride`
  - `visible_state`
  - `disabled_actions`
  - `enabled_actions`
  - `action_overrides`
- `DynamicRule`
  - `rule_id`
  - `priority`
  - `when`
  - `apply`

### Merge Semantics

- start from the authored object and authored action effect
- collect all active dynamic rules for the current time
- apply them in ascending priority, with higher priority overriding lower
- build one effective object view and one effective action effect per action

This makes the default case explicit and keeps special windows local.

## Execution Semantics

The recommended step semantics are:

1. resolve active dynamic rules from the current step start time
2. build effective object and action views
3. execute the action against the effective action definition
4. commit the action's immediate state changes
5. apply action cost, including time advance
6. re-resolve dynamic rules using the new time
7. project observation from the new effective state
8. run static event rules and termination checks

### Why Resolve At Step Start

Actions should use the time at which they begin, not the time after their cost is
charged.

Example:

- at 09:59 a breakfast payout window is still active
- selling the item should use the breakfast payout
- after the step, time may become 10:07
- the next step should then use the normal payout

This rule is easy to reason about and easy to test.

## Mechanism 1: Business Hours

### Purpose

Business hours force the agent to schedule actions rather than treating every
service as permanently available.

### Desired Environment Effect

- the object remains visible in the environment
- the agent can see whether it is open
- actions fail cleanly when attempted outside operating hours
- long loops must account for whether payout or resupply locations are still open

### Recommended Expression

Business hours should affect both:

- object `visible_state`
- action availability

Example:

```yaml
dynamic_rules:
  - rule_id: service_depot_open
    priority: 100
    when:
      time_window:
        start: "09:00"
        end: "17:00"
    apply:
      object_overrides:
        pickup_clerk:
          visible_state:
            open: true
          enabled_actions: ["collect_service_fee"]

  - rule_id: service_depot_closed
    priority: 90
    when:
      not:
        time_window:
          start: "09:00"
          end: "17:00"
    apply:
      object_overrides:
        pickup_clerk:
          visible_state:
            open: false
          disabled_actions: ["collect_service_fee"]
```

### What This Changes For The Agent

- repair work is no longer a timeless payout loop
- cashing out too late means carrying the ticket overnight
- the agent may need to choose between another production step and going to the
  depot before close

## Mechanism 2: Price Windows

### Purpose

Price windows make buy and sell decisions time-sensitive without requiring random
simulation.

### Desired Environment Effect

- the same object can have a different price at different times
- the displayed price matches the executed value
- the agent can choose to buy now, sell later, or wait for a cheaper window

### Recommended Expression

Price windows should override both:

- the displayed value in `visible_state`
- the real numeric fields in the effective action effect

Example:

```yaml
dynamic_rules:
  - rule_id: breakfast_meal_bonus
    priority: 100
    when:
      time_window:
        start: "06:00"
        end: "10:00"
    apply:
      object_overrides:
        meal_counter:
          visible_state:
            meal_box_payout: 8
          action_overrides:
            sell_meal_box:
              money_delta: 8

  - rule_id: meal_default_price
    priority: 10
    when: {}
    apply:
      object_overrides:
        meal_counter:
          visible_state:
            meal_box_payout: 5
          action_overrides:
            sell_meal_box:
              money_delta: 5
```

### What This Changes For The Agent

- meal production can temporarily become better than tea or repair
- the agent may choose to stage inventory for the next window
- the environment now rewards timing, not only local action sequence knowledge

## Mechanism 3: Short-Lived High-Value Windows

### Purpose

Short-lived windows create moments where the current plan should be interrupted.

### Desired Environment Effect

- a narrow window temporarily dominates normal value
- the agent should sometimes abandon a familiar loop to exploit it
- missing the window should be a real lost opportunity

### Recommended Expression

This is structurally the same as a price window, but the duration is shorter and
the incentive is stronger.

Example:

```yaml
dynamic_rules:
  - rule_id: lunch_rush
    priority: 120
    when:
      time_window:
        start: "11:30"
        end: "12:30"
    apply:
      object_overrides:
        meal_counter:
          visible_state:
            rush_order: true
            meal_box_payout: 10
          action_overrides:
            sell_meal_box:
              money_delta: 10
```

### What This Changes For The Agent

- route choice matters because arriving late destroys the advantage
- fast energy recovery can become worth paying for if it preserves access to the
  rush window
- the best action may change mid-episode

## Recommended Presentation In Observation

The observation should make dynamic state explicit enough to support reasoning
without handing the full simulator logic to the agent.

Recommended visible fields:

- `open`
- `current_price`
- `current_payout`
- `shift`
- `rush_order`
- `window_ends_at`

Recommended authored signal objects:

- operations board
- buyer notice
- service shift board
- cafe rush notice

These can provide human-readable summaries of the same underlying dynamic state.

## Recommended `multi_area_town` Design

The best first target is `multi_area_town`, because it already contains several
competing loops with travel, recovery, inventory pressure, and multiple sell
points.

### Tea Loop Dynamics

- `goods_buyer.sell_packed_tea`
  - default payout: 14
  - shortage window: 14:00-16:00 payout becomes 16

Effect on planning:

- tea can be produced before the window and sold later
- the agent must decide whether holding inventory is worth the delay

### Meal Loop Dynamics

- `meal_counter.sell_meal_box`
  - breakfast window: 06:00-10:00 payout becomes 8
  - normal payout: 5
  - lunch rush: 11:30-12:30 payout becomes 10

Effect on planning:

- meal boxes move from backup recovery loop to time-sensitive profit loop
- the agent may prioritize meal prep ahead of lunch rather than using it only
  when cash is low

### Repair Loop Dynamics

- `pickup_clerk.collect_service_fee`
  - service depot open only from 09:00-17:00

Effect on planning:

- repair creates cashflow only if the ticket can be redeemed during opening hours
- the agent may need to stop producing and cash out before close

### Recovery Dynamics

- `barista.buy_coffee`
  - available from 07:00-18:00
- `bed.sleep_shift`
  - always available, but slow and costly in time

Effect on planning:

- the environment provides a meaningful choice between paying for speed and
  sacrificing time for free recovery

## Why These Dynamics Are Good First Targets

- they are deterministic
- they are easy to expose in observation
- they alter planning without introducing hidden randomness
- they interact naturally with existing movement, energy, and inventory systems
- they create schedule pressure without requiring a full economy simulator

## Recommended Implementation Boundaries

The first implementation should avoid:

- stochastic demand or prices
- interdependent market-clearing systems
- hidden rules that require guessing
- permanent mutation of base scenario prices due to time windows

The first implementation should guarantee:

- one source of truth for effective availability and effective prices
- identical logic for observation and action execution
- stable behavior under a fixed seed
- boundary tests for every time window

## Testing Strategy

At minimum, add tests for:

- business-hour boundary behavior
  - open at 08:59, closed at 09:00 or vice versa depending on the chosen interval
- observation and execution consistency
  - displayed payout equals realized payout
- priority resolution
  - lunch rush overrides normal payout
- carryover across steps
  - the same action is profitable in one step and normal in the next after time
    advances past the window
- route-sensitive opportunity cost
  - arriving after a short window produces the lower default reward

## Suggested Rollout Plan

1. Add deterministic dynamic-rule support with time windows only.
2. Enable business hours on one service location and one recovery location.
3. Enable one daily price window and one short rush window.
4. Update `multi_area_town` to include explicit visible signals for the active
   window.
5. Add scenario and transition tests before exploring any stochastic dynamics.

This is enough to turn TownBench from a static loop benchmark into a benchmark
that tests time-sensitive planning and adaptive economic behavior.
