from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from engine.state import (
    ActionCost,
    AgentState,
    Location,
    ObjectActionEffect,
    Skill,
    TerminationConfig,
    WorldEventRule,
    WorldObject,
    WorldState,
)
from scenario.schema import ScenarioConfig


def load_scenario(path: Union[str, Path]) -> WorldState:
    scenario_path = Path(path).resolve()
    config = ScenarioConfig.model_validate(yaml.safe_load(scenario_path.read_text(encoding="utf-8")))
    base_dir = scenario_path.parent

    _ensure_unique_ids([item.location_id for item in config.locations], "location")
    _ensure_unique_ids([item.object_id for item in config.objects], "object")
    _ensure_unique_ids([item.skill_id for item in config.skills], "skill")
    _ensure_unique_ids([item.event_id for item in config.event_rules], "event rule")

    locations = {
        item.location_id: Location(
            location_id=item.location_id,
            name=item.name,
            description=item.description,
            links=list(item.links),
            tags=list(item.tags),
            object_ids=[],
        )
        for item in config.locations
    }

    if config.initial_agent_state.location_id not in locations:
        raise ValueError(
            f"Initial agent location `{config.initial_agent_state.location_id}` does not exist in locations."
        )
    _validate_location_links(locations)

    objects: dict[str, WorldObject] = {}
    for item in config.objects:
        if item.location_id not in locations:
            raise ValueError(f"Object `{item.object_id}` references unknown location `{item.location_id}`.")
        if set(item.action_effects) - set(item.action_ids):
            raise ValueError(
                f"Object `{item.object_id}` has action_effects that are not exposed in action_ids."
            )

        resource_content = None
        if item.resource_file:
            resource_content = _read_text(base_dir / item.resource_file)

        objects[item.object_id] = WorldObject(
            object_id=item.object_id,
            name=item.name,
            object_type=item.object_type,
            location_id=item.location_id,
            summary=item.summary,
            visible_state=dict(item.visible_state),
            action_ids=list(item.action_ids),
            tags=list(item.tags),
            inspectable=item.inspectable,
            readable=item.readable,
            actionable=item.actionable or bool(item.action_effects),
            resource_content=resource_content,
            action_effects={
                action_id: ObjectActionEffect(
                    message=effect.message,
                    set_visible_state=dict(effect.set_visible_state),
                    set_world_flags=dict(effect.set_world_flags),
                )
                for action_id, effect in item.action_effects.items()
            },
        )
        locations[item.location_id].object_ids.append(item.object_id)

    skills = {
        item.skill_id: Skill(
            skill_id=item.skill_id,
            title=item.title,
            content=_read_text(base_dir / item.file),
        )
        for item in config.skills
    }

    _validate_event_rules(config, objects)

    return WorldState(
        current_time=config.initial_world_state.current_time,
        agent=AgentState(**config.initial_agent_state.model_dump()),
        locations=locations,
        objects=objects,
        skills=skills,
        opening_briefing=config.opening_briefing,
        public_rules=list(config.public_rules),
        world_flags=dict(config.initial_world_state.world_flags),
        action_costs={
            action_type: ActionCost(
                time_delta=cost.time_delta,
                money_delta=cost.money_delta,
                energy_delta=cost.energy_delta,
                inventory_delta=dict(cost.inventory_delta),
            )
            for action_type, cost in config.action_costs.items()
        },
        event_rules=[
            WorldEventRule(
                event_id=rule.event_id,
                required_world_flags=dict(rule.required_world_flags),
                set_world_flags=dict(rule.set_world_flags),
                set_object_visible_state={
                    object_id: dict(patch) for object_id, patch in rule.set_object_visible_state.items()
                },
                trigger_once=rule.trigger_once,
            )
            for rule in config.event_rules
        ],
        termination_config=TerminationConfig(**config.termination_config.model_dump()),
        scenario_id=config.scenario_id,
        seed=config.seed,
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _ensure_unique_ids(values: list[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate {label} id(s): {duplicate_list}.")


def _validate_location_links(locations: dict[str, Location]) -> None:
    known_locations = set(locations)
    for location in locations.values():
        unknown_links = sorted(set(location.links) - known_locations)
        if unknown_links:
            links = ", ".join(unknown_links)
            raise ValueError(f"Location `{location.location_id}` links to unknown location(s): {links}.")


def _validate_event_rules(config: ScenarioConfig, objects: dict[str, WorldObject]) -> None:
    known_objects = set(objects)
    for rule in config.event_rules:
        unknown_objects = sorted(set(rule.set_object_visible_state) - known_objects)
        if unknown_objects:
            object_list = ", ".join(unknown_objects)
            raise ValueError(f"Event rule `{rule.event_id}` references unknown object(s): {object_list}.")
