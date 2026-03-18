# Phase 1 Economic Expansion Plan

## Goal

Define the first meaningful expansion of TownBench as a compact economic environment.

Phase 1 should stay simple enough to debug from traces, but rich enough that the agent is no longer solving one obvious scripted loop. The environment should support several ways to make money, several ways to spend money, and clear tradeoffs between short-term survival and medium-term profit.

This phase is intentionally limited. It should not yet depend on deep simulation, large inventories, reputation systems, or complex hidden-state mechanics.

## Phase 1 Design Target

By the end of Phase 1, one town should support:

- 4 earning loops
- 4 spending sinks
- 6 to 8 locations
- 10 to 16 economically relevant objects
- a mix of public work, production work, and small investment choices
- multiple plausible strategies with no single dominant one in every episode

The main benchmark question in this phase is:

- can the agent choose among multiple profitable actions under money, time, and energy pressure?

## Core Capability To Test

Phase 1 should test whether an agent can:

- compare several visible income opportunities
- recognize that some spending is investment rather than waste
- preserve enough energy to keep operating
- avoid low-value distractions
- switch between quick cash and setup-heavy profit

## Economic Structure

Phase 1 should introduce a small but legible town economy built from four layers:

- public jobs
- small commerce
- basic processing
- recovery and mobility spending

This is enough to create branching behavior without turning the environment into a full management simulator.

## Proposed Town Layout

### 1. Plaza

Role:

- public hub
- first place the agent understands available work

Add:

- `job_board`
- `delivery_board`
- `public_bench`

Economic purpose:

- exposes low-risk earning opportunities
- gives the agent immediate fallback options when low on money

### 2. Market

Role:

- simple buying and selling hub

Add:

- `produce_stall`
- `tea_vendor`
- `general_buyer`

Economic purpose:

- supports small trading and raw material purchase
- lets the agent convert cash into materials or immediate resale opportunities

### 3. Workshop

Role:

- transformation and production hub

Add:

- `tea_station`
- `packaging_table`
- `repair_corner`

Economic purpose:

- turns low-value inputs into higher-value outputs
- supports more profitable but more step-heavy earning paths

### 4. Library

Role:

- knowledge and procedural support

Add:

- `recipe_shelf`
- `trade_notes`
- `archive_book`

Economic purpose:

- gives operational hints
- contains at least one useful guide and one distractor document

### 5. Canteen

Role:

- energy recovery sink

Add:

- `meal_counter`
- `cheap_snack_rack`

Economic purpose:

- converts money into energy
- creates a meaningful survival-versus-profit tradeoff

### 6. Station

Role:

- optional speed purchase

Add:

- `express_cart`
- `schedule_board`

Economic purpose:

- converts money into reduced travel friction or faster access to opportunities

### 7. Supply Shop

Role:

- tool and input purchase

Add:

- `tool_rack`
- `material_crate`

Economic purpose:

- sells one or two small upgrades and basic materials
- creates the first investment decision in the environment

## Primary Earning Loops

Phase 1 should include four distinct money-making paths.

## Loop A: Public Delivery Work

### Summary

Take a posted job, pick up an item, bring it to the right place, collect payment.

### Why It Exists

- gives the agent a low-complexity baseline
- provides reliable income when the agent has little money or knowledge

### Economic Profile

- low startup cost
- low profit
- moderate travel cost
- low information requirement

### Typical Components

- `delivery_board`
- pickup object
- dropoff ledger or clerk

### Benchmark Value

This is the safe fallback strategy. It should be good enough to keep the agent alive, but not so good that it dominates every other path.

## Loop B: Tea Processing Work

### Summary

Acquire or locate tea input, use the workshop to prepare it, package it, then hand it off for payout.

### Why It Exists

- extends the current tea loop into a more economic workflow
- introduces multi-step production without making the graph too large

### Economic Profile

- medium startup cost
- medium to high profit
- medium information requirement
- more steps than delivery work

### Typical Components

- `tea_vendor` or `material_crate`
- `tea_station`
- `packaging_table`
- payout ledger or buyer

### Benchmark Value

This is the first setup-heavy path that should outperform simple delivery if the agent executes it cleanly.

## Loop C: Small Arbitrage

### Summary

Buy an item cheaply at one location and sell it at a better price somewhere else.

### Why It Exists

- introduces simple market reasoning without requiring a dynamic price simulator
- tests whether the agent notices public pricing clues

### Economic Profile

- low to medium startup cost
- low step count
- profit depends on noticing price spread
- can be repeated but should not be overpowered

### Typical Components

- seller at `market`
- buyer elsewhere, such as `plaza` or `canteen`
- one short note or visible clue indicating demand

### Benchmark Value

This tests whether the agent can exploit visible economic differences rather than only follow formal jobs.

## Loop D: Knowledge-Gated Service

### Summary

Read the right document or guide, then complete a specialized but short service task for better payout.

### Why It Exists

- creates a reason to read, but not read everything
- makes knowledge economically relevant

### Economic Profile

- low material cost
- medium to high payout
- requires targeted information gathering
- lower physical complexity than production work

### Typical Components

- useful library document
- one specialized workstation or service counter
- payout object or customer order

### Benchmark Value

This is the first path that rewards selective information acquisition.

## Spending Sinks

Phase 1 should add at least four distinct reasons to spend money.

## Sink A: Meals And Snacks

### Purpose

Recover energy so the agent can keep acting profitably.

### Design Requirement

- one cheap low-recovery option
- one more expensive high-recovery option

### Benchmark Function

Tests whether the agent understands spending for continued operation instead of hoarding cash blindly.

## Sink B: Transport

### Purpose

Pay to save time or reduce travel burden.

### Design Requirement

- a small fee that is sometimes worth paying
- not required for every profitable plan

### Benchmark Function

Tests whether the agent can convert money into speed when deadlines or distance make it worthwhile.

## Sink C: Tools

### Purpose

Unlock better earning options or improve margins.

### Candidate Examples

- kettle upgrade
- packaging kit
- handcart
- repair tool

### Benchmark Function

Tests whether the agent recognizes medium-term investment.

## Sink D: Materials

### Purpose

Purchase consumables needed for a production chain.

### Candidate Examples

- tea leaves
- cups
- wrapping paper
- simple spare parts

### Benchmark Function

Tests whether the agent can treat money as working capital instead of only as final score.

## Recommended Objects

The following objects are enough for a good first version.

### Public Work Objects

- `job_board`
- `delivery_board`
- `completion_ledger`

### Production Objects

- `tea_station`
- `packaging_table`
- `repair_corner`

### Commerce Objects

- `produce_stall`
- `tea_vendor`
- `general_buyer`
- `material_crate`

### Recovery And Mobility Objects

- `meal_counter`
- `cheap_snack_rack`
- `express_cart`

### Information Objects

- `recipe_shelf`
- `trade_notes`
- `archive_book`

## Recommended Documents

Phase 1 should include a small document set with distinct value levels.

### Useful Operational Documents

- tea preparation note
- packaging instruction card
- short market note indicating one profitable resale
- transport schedule summary

### Distractor Documents

- town history note
- cultural tea essay
- non-actionable archive excerpt

The benchmark should reward selective reading rather than exhaustive reading.

## Recommended Skills

Skills in Phase 1 should stay lightweight and directly tied to earnings.

### `delivery_basics`

- how posted delivery jobs are settled

### `tea_basics`

- the minimum sequence for processing tea work

### `packaging_rules`

- how to turn prepared goods into payout-ready goods

### `market_observation`

- how to use visible clues to spot small arbitrage

### `town_history`

- distractor

## Example Agent Strategies

Phase 1 should support several valid styles of play.

### Strategy 1: Safe Worker

- rely on public jobs
- buy food only when needed
- avoid investment

Expected profile:

- stable
- lower total profit
- easy for weak agents

### Strategy 2: Small Trader

- exploit one or two resale opportunities
- use little reading
- preserve cash and move efficiently

Expected profile:

- moderate profit
- depends on noticing simple price differences

### Strategy 3: Setup Investor

- buy one tool or material batch
- use workshop loops
- accept lower early cash for higher later returns

Expected profile:

- weak early game
- better medium-horizon profit

### Strategy 4: Selective Reader

- read only one or two high-value documents
- unlock specialized tasks
- avoid flavor-only resources

Expected profile:

- information-efficient
- strong if the agent filters well

## Failure Modes The Environment Should Expose

Phase 1 should make common weak-agent errors legible.

### Error A: Blind Hoarding

- refuses to spend on food, transport, or materials
- appears cash-conservative but becomes strategically stuck

### Error B: Blind Consumption

- spends on every available convenience
- maintains energy but destroys profit

### Error C: Short-Horizon Greed

- repeatedly takes low-value jobs
- never invests in higher-margin paths

### Error D: Information Overconsumption

- reads every skill and document
- loses too much time for the value gained

### Error E: Shallow Exploration

- never inspects enough locations to discover better loops

## Balance Targets

Phase 1 does not need exact numeric tuning in this document, but it should respect several relationships.

### Baseline Relationship

- delivery work should be the safest but not the most profitable
- production work should beat delivery if executed cleanly
- arbitrage should be efficient but capped
- knowledge-gated work should be strong only if the right document is chosen

### Spending Relationship

- food should usually be worth buying at least once in a long episode
- transport should sometimes be worth buying, not always
- tools should pay back only if the agent uses them repeatedly
- materials should create margin, not guaranteed free profit

## Scope Boundary For Phase 1

Do not add these yet:

- deep reputation systems
- large hidden-object systems
- stochastic market simulation
- multi-day persistent town memory
- social faction conflict
- complicated legal or permit structures

Those belong in later phases.

## Suggested Rollout Inside Phase 1

Phase 1 can itself be introduced in three internal steps.

### Step 1: Branching Income

Add:

- delivery loop
- tea processing loop
- meals as spending sink

Result:

- benchmark moves beyond a single authored path

### Step 2: Investment And Mobility

Add:

- transport fee option
- first useful tool purchase
- one small arbitrage loop

Result:

- benchmark begins testing investment and speed tradeoffs

### Step 3: Selective Information Value

Add:

- one strong operational document
- one strong distractor document
- one knowledge-gated service task

Result:

- benchmark begins testing whether the agent can read selectively

## Recommended First Scenario Family

The first Phase 1 town should feel like a modest working district, not a giant city.

Good theme:

- small trade town
- tea and food work
- public jobs
- short walking distances
- a few practical workshop tasks

That theme stays close to the current `demo_town` identity while expanding the economy enough to become a real benchmark.

## Success Condition For The Phase

Phase 1 is successful when:

- different agents visibly choose different earning paths
- spending behavior becomes strategically meaningful
- a simple baseline can survive, but stronger agents profit more
- traces show genuine planning choices rather than only linear task execution

## Next Step After This Phase

Once Phase 1 works, the next environment expansion should be Phase 2 resource closure:

- more explicit material chains
- maintenance costs
- inventory pressure
- recurring operational loops

That is the point where TownBench begins to move from "economic choice environment" toward "compact simulation benchmark."
