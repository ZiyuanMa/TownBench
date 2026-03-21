# Multi-Area Town Scenario Draft

## Goal

Define a new area-aware scenario that stays faithful to `phase2_town` instead of replacing it with a different theme.

The scenario should validate the new `Area` mechanic while reusing as much of the existing phase2 authoring pattern as possible:

- keep the same town-scale economic loop style
- keep the same item economy where practical
- keep the same "choose a loop under money / energy / inventory constraints" structure
- make `Area` matter by splitting the old flat map into multi-room districts

Recommended `scenario_id`: `multi_area_town`

## Design Principles

1. reuse `phase2_town` objects, prices, and loop structure before inventing new mechanics
2. add only a small number of new actions that highlight recovery and routing tradeoffs
3. keep the scenario town-centric: buildings are important, but the task is still moving around town to make money and recover
4. make at least one profitable loop require moving across multiple rooms inside the same `Area`

## Area Layout

The scenario is organized into five areas.

### `market_block`

- `plaza`
- `market`
- `supply_shop`
- `fuel_counter`

This remains the public trade hub and the main routing junction.

### `workshop_building`

- `workshop_lobby`
- `tea_room`
- `packing_room`
- `meal_prep_room`
- `repair_room`

This is the main demonstration area for the new mechanic. Internal movement should rely on shared `area_id`, not authored intra-building links.

### `service_hub`

- `storage_room`
- `service_depot`

This keeps the phase2 capacity-upgrade and repair payout path intact.

### `home_block`

- `home_entry`
- `kitchen`
- `bedroom`

This introduces a low-cost recovery option and a reason to revisit the town when energy is low.

### `cafe_corner`

- `cafe_front`
- `coffee_counter`
- `pickup_window`

This introduces a faster paid recovery option and one alternative sell path.

## Cross-Area Routing

Cross-area movement should stay explicit and simple.

Recommended authored links:

- `plaza` links to `market`, `workshop_lobby`, `storage_room`, `service_depot`, `home_entry`, `cafe_front`
- `market`, `workshop_lobby`, `storage_room`, `service_depot`, `home_entry`, and `cafe_front` each link back to `plaza`

No other cross-area links are required in v1.

This preserves a strong town-hub shape:

- town travel goes through `plaza`
- building travel happens inside one `Area`
- observation should make this distinction obvious through `current_area` and `nearby_locations`

## Reused Phase2 Content

These phase2 objects should be reused almost verbatim, changing only `location_id` where needed.

### Market-side objects

- `operations_board` at `plaza`
- `tea_wholesaler` at `market`
- `ingredient_seller` at `market`
- `bargain_bin` at `market`
- `tea_batch_crate` at `market`
- `goods_buyer` at `market`
- `supply_counter` at `supply_shop`
- `fuel_rack` at `fuel_counter`
- `usage_notice` at `fuel_counter`

### Workshop-side objects

- `tea_station` moves from `workshop` to `tea_room`
- `packaging_table` moves from `workshop` to `packing_room`
- `meal_prep_table` moves from `workshop` to `meal_prep_room`
- `repair_bench` moves from `workshop` to `repair_room`

### Service-side objects

- `locker_desk` stays at `storage_room`
- `shelf_space_ledger` stays at `storage_room`
- `pickup_clerk` stays at `service_depot`
- `repair_queue` stays at `service_depot`

## New Support Objects

Only four new support objects are needed in the first version.

### Home recovery

- `pantry_shelf` at `kitchen`
- `bed` at `bedroom`

### Cafe recovery and alt-sale

- `barista` at `coffee_counter`
- `cafe_buyer` at `pickup_window`

## Economy And Actions

The safest approach is to keep existing phase2 economics unchanged for the core loops.

### Core loops to preserve

Tea loop:

1. buy `tea_bundle`
2. buy `fuel_canister`
3. buy `packaging_sleeve`
4. move into `workshop_building`
5. brew in `tea_room`
6. pack in `packing_room`
7. return to `market`
8. sell `packed_tea`

Meal loop:

1. buy `meal_ingredients`
2. move into `meal_prep_room`
3. assemble `meal_box`
4. sell at the meal buyer location

Repair loop:

1. buy `repair_part`
2. move into `repair_room`
3. create `serviced_device_ticket`
4. cash out at `service_depot`

Locker upgrade:

- keep exactly the same one-time upgrade behavior and pricing as `phase2_town`

### New recovery actions

These actions should be intentionally simple.

`pantry_shelf.eat_meal_box`

- requires `meal_box: 1`
- inventory delta: `meal_box: -1`
- energy delta: around `18` to `24`
- no money change

Purpose:
- converts an existing produced item into emergency recovery
- creates a real decision between selling the meal box or consuming it

`bed.sleep_shift`

- no money cost
- high energy recovery, around `40`
- should rely on normal action cost time instead of introducing custom time logic

Purpose:
- lowest-cost recovery path when the agent is cash-poor
- slower than buying food or coffee because it consumes a full action

`barista.buy_coffee`

- required money: around `3`
- money delta: `-3`
- energy delta: around `14` to `18`

Purpose:
- fast paid recovery
- weaker than a full rest but cheaper in time than getting stuck on low-energy paths

`cafe_buyer.sell_packed_tea`

- requires `packed_tea: 1`
- money delta: around `12`
- inventory delta: `packed_tea: -1`

Purpose:
- gives an alternate tea outlet that pays less than `goods_buyer` at `market`
- creates a route tradeoff without changing the main best-profit loop

## Recommended Spatial Beats

The map should force the following useful distinctions:

- `market` is not the same as `supply_shop`
- `tea_room` is not the same as `packing_room`
- `repair_room` is not the same as `meal_prep_room`
- `coffee_counter` is not the same as `pickup_window`
- `home_entry` is not the same as `bedroom`

This matters because the scenario should prove that:

- same-area movement is less tedious than authored room-to-room links
- object access is still precise and room-scoped
- the agent must reason over room function, not just district name

## Public Rules

The scenario should include the new area guidance explicitly.

Recommended addition:

- "Locations may belong to an Area such as a building or district. You can move freely between locations in the same Area. Use `nearby_locations` to see every currently reachable location."

Keep the existing phase2-style rules as much as possible:

- actions cost time and energy
- starting carry limit is visible
- tea loop is the best steady margin
- meal loop is the fallback when cash is low
- repair loop pays well but needs upfront capital
- storage upgrade is one-time and improves throughput

Add two new concise rules:

- home recovery is cheap but costs time
- cafe recovery is faster but costs money

## Resource And Skill Reuse

The scenario can largely reuse the phase2 documentation assets with light edits.

Recommended reuse:

- adapt `operations_board.txt`
- adapt `usage_notice.txt`
- adapt `repair_queue.txt`
- reuse `tea_operations`
- reuse `cashflow_recovery`
- reuse `service_contracts`

Optional additions:

- `recovery_options.md` for home vs cafe recovery guidance
- `town_routing_notes.txt` if navigation hints are needed during early tuning

## Suggested Test Coverage

The scenario should be validated with integration tests close in style to `tests/test_phase2_scenario.py`.

Minimum coverage:

- scenario loads and exposes expected areas and room locations
- tea loop still works, but now requires moving between `tea_room` and `packing_room`
- meal loop still works with the room split
- repair loop still works with the room split
- locker upgrade still enables `tea_batch_crate`
- `cafe_buyer` pays less than `goods_buyer`
- `buy_coffee` restores energy without affecting inventory
- `eat_meal_box` restores energy but consumes sale inventory
- `sleep_shift` recovers energy without requiring money
- attempting to use `packaging_table` from `tea_room` fails until the agent moves to `packing_room`

## Implementation Order

The lowest-risk authoring order is:

1. clone `phase2_town` into `multi_area_town`
2. introduce `areas` and split locations without changing prices or object actions
3. remap workshop objects into room-specific locations
4. update phase2-style tests to the new route structure
5. add home recovery objects and tests
6. add cafe objects and tests
7. tune energy values only after the route and loop tests are stable

## Non-Goals

This scenario should not introduce:

- social simulation
- NPC schedules
- dialogue trees
- narrative quest chains
- area-level object access
- hidden travel rules beyond same-area reachability

It should stay a compact economy benchmark with richer spatial structure.
