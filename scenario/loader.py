from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from engine.state import Location, Skill, WorldObject, WorldState
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
        item.location_id: item.to_location()
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

        objects[item.object_id] = item.to_world_object(
            resource_content=_resolve_resource_content(item, base_dir=base_dir)
        )
        locations[item.location_id].object_ids.append(item.object_id)

    skills = {
        item.skill_id: _load_skill(base_dir / item.file, item.skill_id)
        for item in config.skills
    }

    _validate_event_rules(config, objects, locations)

    return WorldState(
        current_time=config.initial_world_state.current_time,
        agent=config.initial_agent_state.model_copy(deep=True),
        locations=locations,
        objects=objects,
        skills=skills,
        opening_briefing=config.opening_briefing,
        public_rules=list(config.public_rules),
        world_flags=dict(config.initial_world_state.world_flags),
        action_costs={action_type: cost.model_copy(deep=True) for action_type, cost in config.action_costs.items()},
        event_rules=[rule.model_copy(deep=True) for rule in config.event_rules],
        termination_config=config.termination_config.model_copy(deep=True),
        scenario_id=config.scenario_id,
        seed=config.seed,
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _resolve_resource_content(item, *, base_dir: Path) -> str | None:
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


def _validate_event_rules(
    config: ScenarioConfig,
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

    for rule in config.event_rules:
        unknown_objects = sorted(set(rule.set_object_visible_state) - known_objects)
        if unknown_objects:
            object_list = ", ".join(unknown_objects)
            raise ValueError(f"Event rule `{rule.event_id}` references unknown object(s): {object_list}.")
