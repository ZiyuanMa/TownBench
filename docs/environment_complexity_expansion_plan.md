# Environment Complexity Expansion Plan

## Goal

Expand TownBench from a small authored task environment into a staged economic world benchmark.

Implementation-focused design notes for deterministic dynamic mechanisms are
captured in `docs/dynamic_mechanisms_design.md`.

The near-term priority is not code sophistication for its own sake. It is to introduce richer choices:

- more than one way to earn money
- more than one reason to spend money
- meaningful tradeoffs between short-term survival and long-term growth
- situations where the agent must choose among several plausible plans

This document focuses on environment design. It deliberately stays light on implementation details.

## Design Principle

Complexity should be added in layers.

Each phase should introduce one primary source of difficulty:

1. multiple income and spending options
2. resource conversion loops
3. time and market dynamics
4. hidden information and exploration
5. social and institutional consequences

That keeps the benchmark interpretable. If performance changes, it is easier to explain what new capability is being tested.

## Benchmark Direction

The environment should gradually move from:

- "follow a short authored sequence"

to:

- "operate inside a small economy under limited resources and incomplete information"

The target behavior is not just task completion. It is adaptive economic decision-making.

## Phase 1: Multiple Ways To Earn And Spend

### Goal

Make the world economically non-trivial without making it hard to debug.

The agent should face basic questions such as:

- Should I take the quick low-value job or invest in a better path?
- Should I spend now to unlock better earnings later?
- Should I preserve energy or spend aggressively for immediate cash?

### Add To The Environment

- 3 to 5 distinct earning paths
- 3 to 5 distinct spending paths
- 5 to 7 locations instead of a minimal 3-location map
- public clues that point to different economic opportunities
- a few distractors so the agent must choose what is worth following

### Earning Path Types

- delivery work
  - low variance
  - low startup cost
  - moderate travel cost
- processing work
  - buy input material, convert it, sell output
  - higher margin but requires more steps
- retail arbitrage
  - price difference across locations
  - profitable only if the agent notices the spread
- service work
  - fulfill requests from public boards or ledgers
  - reliable but time-sensitive
- knowledge-gated work
  - available only after reading a document or learning a skill
  - highest profit among early content

### Spending Path Types

- food and rest
  - spend money to recover energy
- transport
  - spend money to save time
- tools
  - spend money to unlock better actions or better profit margins
- materials
  - spend money to enter processing chains
- rent or access fees
  - spend money to use special facilities

### What This Phase Tests

- simple return-on-investment reasoning
- choice among several profitable actions
- balancing money, time, and energy

### Example Environment Additions

- `canteen`
  - meal purchase
  - converts money into energy
- `market_stall`
  - buy low-value goods
- `workshop`
  - convert raw goods into higher-value goods
- `station`
  - pay to travel faster
- `job_board`
  - lists short work opportunities

## Phase 2: Resource Loops And Economic Closure

### Goal

Turn earning into a small operating loop rather than isolated payouts.

The agent should now manage:

- cash
- energy
- materials
- partially processed goods
- finished goods

### Add To The Environment

- raw materials
- intermediate products
- finished products
- tool durability or maintenance
- inventory pressure
- recurring upkeep costs

### New Economic Structures

- buy raw tea leaves, brew tea, package tea, sell tea
- buy repair parts, fix devices, earn service payout
- buy ingredients, cook food, sell meal boxes
- pay stall fee, unlock temporary selling location

### New Spending Motivations

- replenishment
  - buy consumable materials
- maintenance
  - repair or recharge tools
- expansion
  - buy storage, cart access, better equipment
- emergency recovery
  - remove penalties after mistakes or exhaustion

### What This Phase Tests

- multi-step planning
- inventory and cashflow management
- avoiding dead ends such as running out of money before a profitable chain pays out

### Example Environment Additions

- `supply_shop`
  - sells materials
- `repair_bench`
  - restores broken or degraded equipment
- `storage_room`
  - supports larger carrying capacity or safer stock
- `packaging_table`
  - converts processed goods into higher-value sellable goods

## Phase 3: Time Windows And Market Dynamics

### Goal

Make the best action depend on when it is taken, not only on static world state.

The agent should no longer be able to memorize one fixed profitable loop for the entire episode.

### Add To The Environment

- jobs with deadlines
- day-part schedules
- rotating public demand
- changing prices
- recurring shifts
- events that open and close windows of profitability

### Example Dynamic Systems

- breakfast food is valuable in the morning, low-value later
- a workshop pays extra only during one shift
- transport is cheap during one window and expensive during another
- some buyers appear only at night
- a market shortage temporarily raises one item's selling price

### Spending Uses In This Phase

- premium travel
  - pay to reach a deadline in time
- rush processing
  - pay extra to finish goods faster
- reservation or slot purchase
  - pay to secure access to a profitable station

### What This Phase Tests

- time-sensitive planning
- opportunity cost awareness
- willingness to abandon a familiar path when market conditions shift

### Example Environment Additions

- `auction_corner`
  - prices fluctuate by time window
- `night_vendor`
  - appears only during a later period
- `express_cart`
  - converts money into reduced travel time
- `shift_board`
  - posts short-lived high-value jobs

## Phase 4: Hidden Information And Information Economy

### Goal

Force the agent to explore, infer, and decide when information is worth paying for.

The world should stop behaving like a fully visible menu of options.

### Add To The Environment

- hidden earning opportunities
- partial clues across documents and locations
- misleading but plausible leads
- optional paid information
- unlockable knowledge sources

### Information Structures

- a public note hints at profitable work but not the full recipe
- one archive explains where to source materials cheaply
- one NPC or desk sells hints
- one guide unlocks an otherwise invisible workflow
- some documents are distractors with thematic but non-operational content

### Spending Uses In This Phase

- buy maps, schedules, or reference access
- pay for training or certification
- pay for market reports
- pay for rumors or partial hints

### What This Phase Tests

- exploration under resource pressure
- deciding whether information is worth buying
- distinguishing useful documents from noise

### Example Environment Additions

- `archive_desk`
  - paid access to local records
- `training_room`
  - unlocks specialized work after payment
- `rumor_board`
  - offers noisy leads
- `permit_office`
  - gated access to regulated work

## Phase 5: Social Systems And Long-Term Consequences

### Goal

Make the environment feel persistent and strategic rather than transactional.

The agent should now face long-horizon tradeoffs:

- exploit now and suffer later
- invest in trust and gain future access
- choose between legal, gray, and risky income streams

### Add To The Environment

- reputation
- permits and compliance
- relationship-based access
- penalties and fines
- health or exhaustion consequences
- recurring obligations

### Social-Economic Structures

- reliable employers pay less but build reputation
- gray-market work pays more but risks fines
- failing jobs damages future opportunities
- paying membership fees unlocks stable premium work
- helping one faction closes another path

### Spending Uses In This Phase

- pay taxes, fees, and renewals
- pay for medical recovery
- pay membership or guild dues
- pay deposits, insurance, or bond requirements

### What This Phase Tests

- long-term planning
- reputation management
- multi-objective decision-making under delayed consequences

### Example Environment Additions

- `guild_hall`
  - access to premium regulated jobs
- `clinic`
  - recover from exhaustion or harmful status
- `inspector_office`
  - fines or compliance checks
- `black_market_corner`
  - high upside with risk

## Cross-Phase Content Categories

Across all phases, expansion should be visible in the same stable content categories.

### Locations

Add locations that each represent one economic role:

- public job discovery
- raw material purchase
- processing
- resale
- recovery
- transport
- information
- regulation

### Objects

Add objects with clear functional meaning:

- boards and ledgers
- purchase points
- transformation stations
- recovery points
- information sources
- permits and records

### Documents And Skills

Documents should not only explain rules. They should create asymmetric access to profit.

Useful document roles:

- recipe
- operating manual
- local schedule
- market report
- certification guide
- archived clue
- distractor lore

### Economic Resources

Even before building a very detailed simulator, the environment should eventually distinguish:

- money
- time
- energy
- inventory
- tools
- access rights
- reputation
- information

## Recommended Rollout Order

The most practical order is:

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4
5. Phase 5

This order matters because:

- Phase 1 creates immediate branching behavior
- Phase 2 turns branching into planning
- Phase 3 makes the plan time-dependent
- Phase 4 makes the world partially hidden
- Phase 5 makes the consequences persistent

## Suggested Scenario Milestones

Each phase can correspond to one scenario family.

### Milestone A: Small Town Economy

- 5 to 7 locations
- several simple jobs
- food, transport, and tools as spending sinks
- clear but non-trivial best path

### Milestone B: Production Town

- material purchase and transformation chains
- inventory bottlenecks
- upkeep and maintenance costs
- multiple profitable operating loops

### Milestone C: Dynamic Market Town

- deadlines
- time windows
- price changes
- temporary opportunities

### Milestone D: Hidden Opportunity Town

- discoverable workflows
- paid information
- partial clues
- deliberate distractors

### Milestone E: Persistent Social Town

- reputation
- permits
- fines
- high-risk versus stable income channels

## Guardrails

Avoid adding complexity that does not create better decisions.

Bad complexity:

- large numbers of nearly identical objects
- random events with no learnable structure
- long action chains that differ only cosmetically
- documents that are verbose but operationally empty

Good complexity:

- several income paths with distinct tradeoffs
- spending that changes future options
- information that can be bought, found, or ignored
- deadlines that reshape priorities
- persistent consequences for strategy choices

## Near-Term Recommendation

The next practical environment milestone should combine only the first two phases.

Target package:

- 3 to 4 earning loops
- 3 spending sinks
- one simple material conversion chain
- one tool purchase that improves future profit
- one recovery location
- one transport shortcut

That is enough to move the benchmark from a toy authored loop into a compact economic environment without making it too hard to reason about.

## Open Questions

- How much hidden information should be introduced before the benchmark stops being easy to debug?
- When should the benchmark move from mostly deterministic authored opportunities to scheduled or stochastic opportunities?
- Should each town emphasize one economic identity, or should one large town contain every system at once?
- When scoring becomes richer later, should benchmark variants reward pure profit, balanced survival, or task diversity?
