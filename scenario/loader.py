from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from engine.rules import inventory_capacity, inventory_load, parse_time_label
from engine.state import Area, Location, Skill, WorldObject, WorldState
from scenario.schema import ScenarioConfig, ScenarioObjectSource


def load_scenario(path: Union[str, Path]) -> WorldState:
    scenario_path = Path(path).resolve()
    config = _parse_config(scenario_path)
    base_dir = scenario_path.parent

    _validate_unique_ids(config)
    areas = _build_areas(config)
    locations = _build_locations(config)
    _validate_location_references(config, locations, areas=areas)
    objects = _build_objects(config, locations=locations, base_dir=base_dir)
    skills = _build_skills(config, base_dir=base_dir)
    _validate_event_rules(config, objects=objects, locations=locations)
    state = _build_world_state(config, areas=areas, locations=locations, objects=objects, skills=skills)
    _validate_initial_agent_capacity(state)
    return state


def _parse_config(scenario_path: Path) -> ScenarioConfig:
    return ScenarioConfig.model_validate(yaml.safe_load(scenario_path.read_text(encoding="utf-8")))


def _validate_unique_ids(config: ScenarioConfig) -> None:
    _ensure_unique_ids([item.area_id for item in config.areas], "area")
    _ensure_unique_ids([item.location_id for item in config.locations], "location")
    _ensure_unique_ids([item.object_id for item in config.objects], "object")
    _ensure_unique_ids([item.skill_id for item in config.skills], "skill")
    _ensure_unique_ids([item.rule_id for item in config.dynamic_rules], "dynamic rule")
    _ensure_unique_ids([item.event_id for item in config.event_rules], "event rule")


def _build_areas(config: ScenarioConfig) -> dict[str, Area]:
    return {item.area_id: item.to_area() for item in config.areas}


def _build_locations(config: ScenarioConfig) -> dict[str, Location]:
    return {item.location_id: item.to_location() for item in config.locations}


def _validate_location_references(
    config: ScenarioConfig,
    locations: dict[str, Location],
    *,
    areas: dict[str, Area],
) -> None:
    if config.initial_agent_state.location_id not in locations:
        raise ValueError(
            f"Initial agent location `{config.initial_agent_state.location_id}` does not exist in locations."
        )
    _validate_location_areas(locations, areas=areas)
    _validate_location_links(locations)


def _build_objects(
    config: ScenarioConfig,
    *,
    locations: dict[str, Location],
    base_dir: Path,
) -> dict[str, WorldObject]:
    objects: dict[str, WorldObject] = {}
    for item in config.objects:
        _validate_object_source(item, locations=locations)
        objects[item.object_id] = item.to_world_object(
            resource_content=_resolve_resource_content(item, base_dir=base_dir)
        )
        locations[item.location_id].object_ids.append(item.object_id)
    return objects


def _build_skills(config: ScenarioConfig, *, base_dir: Path) -> dict[str, Skill]:
    return {item.skill_id: _load_skill(base_dir / item.file, item.skill_id) for item in config.skills}


def _build_world_state(
    config: ScenarioConfig,
    *,
    areas: dict[str, Area],
    locations: dict[str, Location],
    objects: dict[str, WorldObject],
    skills: dict[str, Skill],
) -> WorldState:
    return WorldState(
        current_time=parse_time_label(config.initial_world_state.current_time),
        agent=config.initial_agent_state.model_copy(deep=True),
        areas=areas,
        locations=locations,
        objects=objects,
        skills=skills,
        opening_briefing=config.opening_briefing,
        public_rules=list(config.public_rules),
        world_flags=dict(config.initial_world_state.world_flags),
        action_costs={action_type: cost.model_copy(deep=True) for action_type, cost in config.action_costs.items()},
        dynamic_rules=[rule.model_copy(deep=True) for rule in config.dynamic_rules],
        event_rules=[rule.model_copy(deep=True) for rule in config.event_rules],
        termination_config=config.termination_config.model_copy(deep=True),
        scenario_id=config.scenario_id,
        seed=config.seed,
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _resolve_resource_content(item: ScenarioObjectSource, *, base_dir: Path) -> str | None:
    if item.resource_file:
        return _read_text(base_dir / item.resource_file)
    return item.resource_content


def _load_skill(path: Path, skill_id: str) -> Skill:
    raw_content = _read_text(path)
    metadata, content = _parse_skill_document(raw_content, path=path)
    return Skill(
        skill_id=skill_id,
        name=metadata["name"],
        description=metadata["description"],
        content=content,
    )


def _parse_skill_document(raw_content: str, *, path: Path) -> tuple[dict[str, str], str]:
    if not raw_content.startswith("---\n"):
        raise ValueError(f"Skill file `{path}` must begin with YAML frontmatter.")

    closing_delimiter = raw_content.find("\n---\n", 4)
    if closing_delimiter == -1:
        raise ValueError(f"Skill file `{path}` must close its YAML frontmatter with `---`.")

    metadata_block = raw_content[4:closing_delimiter]
    body = raw_content[closing_delimiter + len("\n---\n"):].strip()
    metadata = yaml.safe_load(metadata_block) or {}

    if not isinstance(metadata, dict):
        raise ValueError(f"Skill file `{path}` frontmatter must be a YAML mapping.")

    name = _require_skill_metadata_string(metadata, "name", path=path)
    description = _require_skill_metadata_string(metadata, "description", path=path)
    if not body:
        raise ValueError(f"Skill file `{path}` must contain non-empty markdown content after frontmatter.")

    return {"name": name, "description": description}, body


def _require_skill_metadata_string(metadata: dict[str, object], field_name: str, *, path: Path) -> str:
    value = metadata.get(field_name)
    if not isinstance(value, str):
        raise ValueError(
            f"Skill file `{path}` must define `{field_name}` as a non-empty string in frontmatter."
        )

    normalized = value.strip()
    if not normalized:
        raise ValueError(
            f"Skill file `{path}` must define `{field_name}` as a non-empty string in frontmatter."
        )
    return normalized


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


def _validate_location_areas(locations: dict[str, Location], *, areas: dict[str, Area]) -> None:
    known_areas = set(areas)
    for location in locations.values():
        if location.area_id is None:
            continue
        if location.area_id not in known_areas:
            raise ValueError(
                f"Location `{location.location_id}` references unknown area `{location.area_id}`."
            )


def _validate_object_source(item: ScenarioObjectSource, *, locations: dict[str, Location]) -> None:
    if item.location_id not in locations:
        raise ValueError(f"Object `{item.object_id}` references unknown location `{item.location_id}`.")
    if set(item.action_effects) - set(item.action_ids):
        raise ValueError(
            f"Object `{item.object_id}` has action_effects that are not exposed in action_ids."
        )


def _validate_event_rules(
    config: ScenarioConfig,
    *,
    objects: dict[str, WorldObject],
    locations: dict[str, Location],
) -> None:
    known_objects = set(objects)
    known_locations = set(locations)

    for world_object in objects.values():
        for action_name, effect in world_object.action_effects.items():
            move_target = effect.move_to_location_id
            if move_target and move_target not in known_locations:
                raise ValueError(
                    f"Object `{world_object.object_id}` action `{action_name}` references unknown location "
                    f"`{move_target}`."
                )

    for rule in config.dynamic_rules:
        for object_id, override in rule.apply.object_overrides.items():
            world_object = objects.get(object_id)
            if world_object is None:
                raise ValueError(f"Dynamic rule `{rule.rule_id}` references unknown object `{object_id}`.")
            unknown_disabled_actions = sorted(set(override.disabled_actions) - set(world_object.action_ids))
            if unknown_disabled_actions:
                action_list = ", ".join(unknown_disabled_actions)
                raise ValueError(
                    f"Dynamic rule `{rule.rule_id}` disables unknown action(s) on `{object_id}`: {action_list}."
                )
            unknown_enabled_actions = sorted(set(override.enabled_actions) - set(world_object.action_ids))
            if unknown_enabled_actions:
                action_list = ", ".join(unknown_enabled_actions)
                raise ValueError(
                    f"Dynamic rule `{rule.rule_id}` enables unknown action(s) on `{object_id}`: {action_list}."
                )
            unknown_action_overrides = sorted(set(override.action_overrides) - set(world_object.action_ids))
            if unknown_action_overrides:
                action_list = ", ".join(unknown_action_overrides)
                raise ValueError(
                    f"Dynamic rule `{rule.rule_id}` overrides unknown action(s) on `{object_id}`: {action_list}."
                )

    for rule in config.event_rules:
        unknown_objects = sorted(set(rule.set_object_visible_state) - known_objects)
        if unknown_objects:
            object_list = ", ".join(unknown_objects)
            raise ValueError(f"Event rule `{rule.event_id}` references unknown object(s): {object_list}.")


def _validate_initial_agent_capacity(state: WorldState) -> None:
    carry_limit = inventory_capacity(state)
    if carry_limit is not None and inventory_load(state.agent.inventory) > carry_limit:
        raise ValueError(
            "Initial agent inventory exceeds the configured carry_limit."
        )
