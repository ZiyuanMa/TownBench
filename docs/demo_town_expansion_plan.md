# Demo Town Expansion Plan

## Goal

Expand `demo_town` from a minimal toy environment into a medium-complexity town that is still easy to inspect manually.

The scenario should stay economically grounded. The agent is not trying to "win" by finishing a single task. It is trying to preserve and improve its economic state over time, and tea orders are one available money-making activity inside that loop.

## Core Direction

`demo_town` should remain aligned with TownBench's current scoring model:

- the important outcomes are `final_money` and `survived_days`
- tasks are instruments for earning money, not terminal goals
- the scenario should discourage blind action through time and energy costs
- success-like world states can exist for legibility, but they should not define the whole benchmark

This means the expansion should stop framing the episode as "complete the tea order to succeed" and instead frame it as "use public information, skills, and movement efficiently to earn money from tea work."

## Scope

This plan focuses on extending scenario content first, with one small engine addition:

- object actions should support `money_delta`

The rest of the first version should stay within the current primitives:

- `open_resource`
- `load_skill`
- `call_action`
- `world_flags`
- `event_rules`
- action costs

No large reward system, inventory economy, or planner-specific logic is required in the first pass.

## Design Principles

- Keep the town small enough to debug from raw traces.
- Make money the stable objective and authored tasks the local mechanism.
- Increase difficulty through tradeoffs, not opaque rules.
- Keep skills useful but not all worth loading.
- Add a few plausible distractors instead of a large amount of noise.
- Preserve deterministic, testable authored behavior.

## Target Difficulty

The upgraded scenario should roughly have:

- 3 locations
- 5 to 6 objects
- 4 skills
- 1 primary earning loop
- 1 to 2 distractors
- an efficient earning path of about 5 to 8 steps

## Proposed Economic Loop

The main earning loop is a tea fulfillment job:

1. read the active order
2. decide which skill or document is worth reading
3. move to the workshop
4. verify supplies if useful
5. brew the tea
6. record or hand off the completed order
7. receive payment

Important constraint:

- brewing tea is not the goal
- logging completion is not the goal
- payment is the economically relevant outcome

The episode should usually continue after an order is completed unless a separate horizon or failure condition ends it.

## Locations

Keep the current three locations:

- `plaza`
  - public notices
  - visible demand for work
  - public updates after production or delivery
- `library`
  - reference materials
  - one optional helper document
  - one distractor document
- `workshop`
  - production area
  - tea station
  - supply shelf
  - completion or pickup record

## Proposed Skills

### `tea_basics`

Purpose:
Core operational skill for brewing tea in the workshop.

Content should tell the agent:

- tea must be brewed in `workshop`
- use `tea_station`
- brewing is the core production step

### `inventory_rules`

Purpose:
Guide the agent to check whether the workshop looks ready before spending time on production.

Content should tell the agent:

- inspect `storage_shelf` before brewing when uncertain
- look for signals such as cups and leaves
- avoid assuming the station is always ready

### `order_fulfillment`

Purpose:
Explain how work turns into money.

Content should tell the agent:

- brewing alone does not create payout
- after brewing, use the completion object to record or hand off the order
- payment is only issued after the completion step

### `tea_history`

Purpose:
Relevant-looking distractor skill.

Content should contain:

- cultural or historical tea notes
- no instructions that improve earnings in the current scenario

The point is to test whether the agent can avoid loading every tea-related skill.

## Proposed Objects

### `notice_board`

Role:
Primary public source of available work.

Behavior:

- readable
- contains the active tea order
- includes payout information
- may mention completion or pickup requirements

### `tea_station`

Role:
Main production object.

Behavior:

- actionable
- exposed action: `brew_tea`
- successful use should set `tea_ready: true`

### `storage_shelf`

Role:
Workshop state check.

Behavior:

- inspectable
- visible state should show stock-like information
- may expose whether cups or leaves are available

### `completion_log`

Role:
Economic settlement object.

Behavior:

- actionable
- exposed action: `record_order`
- successful use should set `order_logged: true`
- successful use should apply `money_delta` to pay the agent

In the first implementation this can remain scenario-authored and permissive.
If needed later, it can gain explicit preconditions.

### `recipe_card`

Role:
Optional helper resource.

Behavior:

- readable
- provides lightweight procedural confirmation
- may save a mistaken trip or unnecessary skill read

### `archive_book`

Role:
Distractor resource.

Behavior:

- readable
- thematically related
- operationally useless for the current earning loop

## Proposed Resources And Skills Layout

Suggested files under `scenarios/demo_town/`:

- `skills/tea_basics.md`
- `skills/inventory_rules.md`
- `skills/order_fulfillment.md`
- `skills/tea_history.md`
- `resources/tea_order.txt`
- `resources/recipe_card.txt`
- `resources/archive_book.txt`

Each skill file should use frontmatter:

```md
---
name: Tea Basics
description: Basic workshop tea preparation steps.
---

# Tea Basics

...
```

## Proposed World Flags

Recommended flags:

- `tea_ready`
  - set after brewing
- `order_logged`
  - set after recording fulfillment
- `tea_announced`
  - optional public update after brewing
- `payment_posted`
  - optional public update after payout

These flags are mainly for authored world feedback and testability, not for defining benchmark success.

## Proposed Event Rules

### Event 1: Tea Ready Notice

Trigger:

- `tea_ready: true`

Effect:

- update the notice board with a production-ready message

Purpose:

- provide legible state feedback after brewing

### Event 2: Order Logged Notice

Trigger:

- `order_logged: true`

Effect:

- update public state to show that the order was processed
- optionally set `payment_posted: true`

Purpose:

- make the money-generating completion step visible in the world

## Economic Outcome

The key authored reward should come from `money_delta` on an object action, most likely `record_order`.

Recommended first version:

- `brew_tea` changes production state only
- `record_order` grants payment
- the reward should be large enough to dominate the action costs of a clean path

This keeps the incentive structure economically meaningful:

- reading too much wastes time
- moving inefficiently wastes time and energy
- skipping the payout step loses money

## Termination Strategy

Do not model the scenario as "one tea order completed equals episode success."

Recommended first version:

- rely on `max_steps` and `stop_on_zero_energy`
- do not use `success_world_flags` for normal order fulfillment
- reserve terminal success flags for special diagnostic scenarios only

This keeps the scenario aligned with the current scorer instead of turning it into a task-completion benchmark.

## Distractor Strategy

Use light distractors only.

Recommended distractors:

- `tea_history` skill
- `archive_book` resource

Optional mild distractor:

- `recipe_card` if its content partly overlaps with useful skills

Distractors should look plausible enough that weak policies may waste time on them, but not so strong that authored traces become noisy or arbitrary.

## Action Cost Tuning

To make economic choices matter:

- keep `load_skill` non-zero cost
- keep `open_resource` cheap but not free
- keep `move_to` and `call_action` meaningfully costly

Suggested direction:

- reading the wrong skill should reduce efficiency
- one useful skill read should still be affordable
- brute-force reading everything should clearly lower net value

## Implementation Phases

### Phase 1: Scenario Expansion Plus `money_delta`

Work items:

- add three new skill files
- add new resource files
- add `completion_log`
- add `recipe_card`
- add `archive_book`
- update the notice board order text to include payout
- add `money_delta` support to object action effects
- make order completion pay the agent
- keep termination horizon-based rather than task-success-based

Expected result:

- richer scenario
- explicit money-generating interactions
- no large engine redesign

### Phase 2: Stronger Economic Constraints

Only do this if phase 1 is too permissive.

High-value additions:

- action preconditions for object actions
- conditional failure when prerequisites are missing
- repeated or rotating orders

Examples:

- `record_order` fails unless `tea_ready` is true
- `brew_tea` fails unless workshop signals look valid
- a new order appears after the previous payout is processed

Expected result:

- cleaner enforcement of economically meaningful action order

## Test Plan

Add or update tests for the following behaviors:

- scenario loader reads all skill metadata and content correctly
- initial observation exposes only skill metadata, not full content
- `load_skill` returns `name`, `description`, and `content`
- `call_action` can apply authored `money_delta`
- trace and step results report the action money delta correctly
- distractor resources are readable but do not affect money directly
- visible world state changes after brewing and after payout

If phase 2 is implemented, also test:

- completion logging fails before brewing
- payout is only granted once per order

## Recommended First Implementation

The first concrete patch should stay small and economic:

- upgrade `demo_town` in place
- add `inventory_rules`, `order_fulfillment`, and `tea_history`
- add `completion_log`, `recipe_card`, and `archive_book`
- add `money_delta` to `ObjectActionEffect`
- make `record_order` pay the agent
- keep episode progression driven by time, energy, and money rather than terminal task success

## Expected Outcome

After this expansion, `demo_town` should be strong enough to test:

- selective skill loading
- movement across locations
- multi-step economic action chains
- payout discipline
- basic distractor resistance
- sensitivity to time and action costs

It should still remain small enough for deterministic tests and manual trace inspection.
