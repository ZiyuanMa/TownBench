# Phase 2 Economic Expansion Plan

## Goal

Define the second environment expansion of TownBench as a compact production economy with recurring operating loops.

Phase 2 should move the benchmark beyond visible branching choices and into cashflow management:

- earnings should come from multi-step operating loops rather than mostly isolated payouts
- spending should include replenishment, maintenance, and capacity decisions
- the agent should be able to enter profitable loops, but also fail by getting stuck mid-loop
- traces should still be interpretable without needing a large simulator

This phase should stay mostly deterministic and authored. The main new difficulty is economic closure, not hidden information or time volatility.

## Phase 2 Design Target

By the end of Phase 2, one town should support:

- 3 to 4 recurring operating loops
- 2 to 3 material chains with at least one intermediate state
- 2 maintenance or upkeep pressures
- 1 light inventory pressure system
- 1 small expansion decision that increases loop throughput
- 7 to 9 locations
- 14 to 20 economically relevant objects

The main benchmark question in this phase is:

- can the agent keep a small business loop running without exhausting cash, energy, or inventory capacity?

## Core Capability To Test

Phase 2 should test whether an agent can:

- plan across several dependent steps before payout
- preserve working capital instead of spending to zero
- recognize replenishment as necessary rather than optional
- choose when a better tool or capacity upgrade is worth buying
- recover from partial progress without entering a dead end

## Structural Change From Phase 1

Phase 1 introduces visible choices among jobs, tools, food, transport, and simple production.

Phase 2 changes the economic shape:

- from one-off opportunities to recurring operating loops
- from simple profit comparison to cashflow sequencing
- from inventory as a small prerequisite list to inventory as a planning constraint
- from "buy tool, unlock action" to "buy, use, maintain, and replenish"

The target feeling is no longer "pick a good job."

It is:

- "run a small operation without mismanaging inputs"

## Economic Structure

Phase 2 should add four new structural pressures on top of Phase 1:

- material closure
- upkeep
- capacity
- recovery after mistakes

These should be visible in the environment, not hidden inside large background systems.

### Material Closure

Profitable loops should consume raw inputs and create intermediate and final goods.

The benchmark should no longer rely mainly on actions that simply mint money.

Good pattern:

- buy or source raw input
- transform it
- optionally package, repair, or combine it
- deliver or sell it
- replenish materials before repeating

### Upkeep

At least one useful loop should require recurring maintenance.

Examples:

- a repair bench consumes charge or parts after several uses
- a brewing station requires fuel packs
- a cart permit expires after several trips

Upkeep should be legible and learnable. It should not be random punishment.

### Capacity

The agent should feel some inventory pressure without turning the environment into a warehouse game.

Good light-weight options:

- carrying limit by item count
- one bulky item class that blocks other pickups
- paid storage that allows batching
- cart rental that expands carrying capacity for a period

### Recovery After Mistakes

Phase 2 should include ways to make recoverable mistakes:

- buying inputs without enough cash to finish the loop
- filling inventory with low-value goods
- wasting one consumable tool use
- over-consuming recovery items and losing working capital

The environment should offer recovery paths, but they should be worse than avoiding the mistake.

## Recommended Town Direction

The Phase 2 town should feel like a production district rather than a general trade square.

Good identity:

- small manufacturing and service town
- tea, meals, packing, and equipment repair
- short to medium routes
- several repeatable loops sharing the same supply network

This keeps continuity with `phase1_town` while making the economy more closed.

## Recommended Town Layout

Phase 2 can extend the existing Phase 1 structure rather than replacing it.

Recommended locations:

- `plaza`
- `market`
- `workshop`
- `canteen`
- `supply_shop`
- `storage_room`
- `service_depot`
- `fuel_counter`

Optional:

- `station`
- `library`

### 1. Market

Role:

- raw input purchase
- output sale
- price comparison anchor

Add:

- `tea_wholesaler`
- `ingredient_seller`
- `goods_buyer`

### 2. Workshop

Role:

- transformation hub
- shared production bottleneck

Add:

- `tea_station`
- `packaging_table`
- `meal_prep_table`
- `repair_bench`

### 3. Supply Shop

Role:

- consumables, tools, maintenance inputs

Add:

- `tool_rack`
- `parts_bin`
- `fuel_shelf`

### 4. Canteen

Role:

- recovery
- one repeatable food production or resale outlet

Add:

- `meal_counter`
- `kitchen_contract_board`

### 5. Storage Room

Role:

- paid capacity expansion
- batch planning support

Add:

- `locker_desk`
- `shelf_space_ledger`

### 6. Service Depot

Role:

- repair and assembly contract payout
- medium-value repeatable service loop

Add:

- `repair_queue`
- `pickup_clerk`

### 7. Fuel Counter

Role:

- upkeep sink
- small but recurring operational cost

Add:

- `fuel_counter`
- `usage_notice`

## Primary Operating Loops

Phase 2 should include recurring loops with different capital and complexity profiles.

## Loop A: Tea Production Loop

### Summary

Buy tea input, brew it, package it, and sell it in repeated cycles.

### Why It Exists

- extends the current Phase 1 tea path into a true operating loop
- provides a clear baseline production business

### Economic Profile

- low to medium startup capital
- medium step count
- repeatable
- sensitive to packaging or fuel replenishment

### Required Structure

- raw tea input
- brewed intermediate item
- packaged output
- one recurring consumable or maintenance cost

### Benchmark Value

Tests whether the agent can repeatedly run a profitable loop without forgetting replenishment costs.

## Loop B: Prepared Meal Loop

### Summary

Buy ingredients, prepare meal boxes, and sell them to a contract buyer.

### Why It Exists

- creates a second production chain with different margins
- shares some infrastructure with other loops

### Economic Profile

- low ingredient cost
- medium energy cost
- moderate payout
- good fallback when larger loops are temporarily unaffordable

### Required Structure

- ingredient purchase
- prep station
- finished meal box
- contract buyer or canteen payout

### Benchmark Value

Tests whether the agent can switch to a lower-capital loop instead of stalling.

## Loop C: Repair Service Loop

### Summary

Buy parts, service devices at the depot, and collect a higher payout.

### Why It Exists

- creates a service-oriented operating loop instead of pure production
- introduces maintenance input and consumable parts

### Economic Profile

- medium startup cost
- fewer transformation steps than production
- higher payout per run
- vulnerable to inventory and parts shortages

### Required Structure

- repair part purchase
- service station
- payout counter
- one failure or waste case if the agent enters underprepared

### Benchmark Value

Tests whether the agent can preserve enough working capital to enter the higher-margin loop.

## Loop D: Batch Trading With Storage

### Summary

Pay for temporary storage or carrying expansion, buy several low-cost goods, and sell them in a more efficient batch.

### Why It Exists

- turns capacity from a passive limit into an economic decision
- creates a non-production loop that still depends on operating structure

### Economic Profile

- medium setup cost
- low per-item complexity
- profit depends on using expanded capacity well

### Required Structure

- low-value bulk good
- carrying pressure
- paid storage or cart access
- resale outlet with better batch economics

### Benchmark Value

Tests whether the agent understands throughput improvements rather than only per-action profit.

## Spending Categories

Phase 2 spending should be organized around business continuity, not only survival.

## Sink A: Replenishment

Purpose:

- buy the consumables needed to keep a loop running

Examples:

- tea bundles
- ingredients
- packaging sleeves
- repair parts
- fuel canisters

Benchmark function:

- forces the agent to reserve working capital

## Sink B: Maintenance

Purpose:

- restore or refresh a productive asset

Examples:

- recharge a bench
- replace a worn tool head
- renew a cart pass

Benchmark function:

- turns profitable tools into ongoing commitments rather than permanent freebies

## Sink C: Capacity Expansion

Purpose:

- improve loop throughput or reduce travel friction

Examples:

- temporary locker rental
- cart rental
- paid shelf space

Benchmark function:

- creates a throughput-vs-cash tradeoff

## Sink D: Recovery

Purpose:

- keep the agent operating after energy or planning mistakes

Examples:

- meals
- quick snacks
- medical patch for overwork penalty

Benchmark function:

- preserves survivability without replacing good planning

## Recommended Objects

### Supply And Input Objects

- `tea_wholesaler`
- `ingredient_seller`
- `parts_bin`
- `fuel_shelf`

### Transformation Objects

- `tea_station`
- `packaging_table`
- `meal_prep_table`
- `repair_bench`

### Sale And Payout Objects

- `goods_buyer`
- `kitchen_contract_board`
- `pickup_clerk`

### Capacity Objects

- `locker_desk`
- `shelf_space_ledger`
- `cart_rental`

### Recovery Objects

- `meal_counter`
- `snack_rack`
- `clinic_desk`

## Recommended Documents

Documents should now support operating efficiency, not only one-time discovery.

Useful operational documents:

- input price sheet
- bench usage guide
- repair parts reference
- meal contract standards
- storage fee notice
- fuel efficiency note

Distractor or lower-value documents:

- local guild history
- old workshop manual with obsolete rates
- scenic town brochure

## Example Agent Strategies

### Strategy 1: Conservative Operator

- run the cheapest loop repeatedly
- keep a cash buffer
- avoid capacity upgrades until stable

### Strategy 2: Throughput Investor

- buy storage or batch capacity early
- accept lower short-term liquidity for stronger repeat profit

### Strategy 3: Loop Switcher

- move between tea, meal, and repair loops depending on current cash and inventory

### Strategy 4: Overextended Speculator

- buys inputs aggressively
- runs out of cash before the loop pays out
- is forced into low-margin recovery behavior

## Failure Modes The Environment Should Expose

### Error A: Zero-Cash Trap

The agent spends down to near zero and cannot afford the last input needed for payout.

### Error B: Dead Inventory

The agent fills capacity with low-value or unfinished goods and blocks better opportunities.

### Error C: Maintenance Neglect

The agent understands a profitable loop once, but fails to account for recurring upkeep.

### Error D: Wrong Upgrade Timing

The agent buys capacity or tools before it can support the resulting operating costs.

### Error E: Shallow Profit Accounting

The agent compares payout amounts but ignores hidden input and maintenance costs.

## Balance Targets

### Baseline Relationship

A simple baseline should be able to survive and complete one low-complexity operating loop.

A stronger baseline should:

- maintain better cashflow
- waste fewer inputs
- exploit at least one medium-margin loop consistently

### Loop Relationship

No single loop should dominate every budget state.

Desired pattern:

- one loop is safest at low cash
- one loop is best at medium capital
- one loop is strongest only after capacity or maintenance investment

### Recovery Relationship

Recovery should be necessary enough to matter, but not so punishing that the town becomes an energy tax benchmark.

### Capacity Relationship

Capacity expansion should be situationally profitable, not mandatory in every successful run.

## Scope Boundary For Phase 2

Phase 2 should not yet add:

- heavy stochastic pricing
- large-scale hidden information
- social factions or reputation ladders
- complex NPC simulation
- deep warehouse management
- multi-day debt systems

Those belong to later phases.

## Suggested Rollout Inside Phase 2

### Step 1: Close One Existing Loop

Take the current tea path and add:

- one consumable upkeep requirement
- one replenishment dependency
- one repeated-sale target

Result:

- Phase 1 production becomes a true operating loop

### Step 2: Add A Second Low-Capital Loop

Add a prepared-meal or small assembly loop using different inputs.

Result:

- the agent gains a fallback when the main loop is unaffordable

### Step 3: Add Maintenance Pressure

Introduce one recurring maintenance sink on a productive asset.

Result:

- the benchmark begins testing total loop cost rather than only gross payout

### Step 4: Add Light Capacity Pressure

Introduce one simple carrying or storage constraint plus one paid expansion path.

Result:

- batching and throughput become economically meaningful

### Step 5: Add Recovery From Bad Inventory States

Ensure the town contains at least one way to unwind partial mistakes, but at a loss.

Result:

- traces show whether the agent can recover instead of only whether it can execute a clean path

## Engine And Scoring Implications

Phase 2 can still stay close to the current TownBench architecture, but it likely needs clearer support for:

- light inventory pressure or carrying limits
- recurring maintenance state
- more explicit operating assets and consumables

Scoring should stay simple in this phase.

Recommended approach:

- keep final money as the primary benchmark score
- retain done, termination reason, and step count as basic run metadata
- avoid making loop-specific diagnostics first-class benchmark scores in Phase 2

If additional analysis is useful during development, it can stay as ad hoc trace inspection rather than becoming part of the formal scorer.

## Success Condition For The Phase

Phase 2 is successful when:

- agents visibly differ in how they manage working capital
- some agents enter profitable loops and sustain them, while weaker ones stall mid-loop
- upgrades are sometimes correct and sometimes premature
- traces show recurring business logic rather than only isolated action chains

At that point TownBench starts to feel like a compact economic simulator rather than a branching authored task environment.
