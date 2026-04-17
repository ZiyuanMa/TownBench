from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from engine.callable_actions import get_callable_action_definitions, matches_callable_action_matcher
from engine.rules import inventory_capacity, inventory_load, parse_time_label
from engine.state import Area, CallableActionMatcher, Location, Skill, WorldObject, WorldState
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
    has_legacy_actions = bool(item.action_ids or item.action_effects)
    has_callable_actions = bool(item.callable_actions)
    if has_legacy_actions and has_callable_actions:
        raise ValueError(
            f"Object `{item.object_id}` must use either legacy action_ids/action_effects or callable_actions, not both."
        )
    if has_callable_actions:
        for action_name, callable_action in item.callable_actions.items():
            if not callable_action.routes:
                raise ValueError(
                    f"Object `{item.object_id}` callable action `{action_name}` must declare routes."
                )
            if len(callable_action.arguments) > 1:
                raise ValueError(
                    f"Object `{item.object_id}` callable action `{action_name}` may declare at most one argument."
                )
            for argument_name, argument_spec in callable_action.arguments.items():
                if not argument_spec.options:
                    raise ValueError(
                        f"Object `{item.object_id}` callable action `{action_name}` argument `{argument_name}` "
                        "must declare at least one enum option."
                    )

            seen_routes: set[tuple[tuple[str, str], ...]] = set()
            for route in callable_action.routes:
                unknown_arguments = sorted(set(route.match) - set(callable_action.arguments))
                if unknown_arguments:
                    argument_list = ", ".join(unknown_arguments)
                    raise ValueError(
                        f"Object `{item.object_id}` callable action `{action_name}` references unknown argument(s): "
                        f"{argument_list}."
                    )
                missing_arguments = sorted(
                    argument_name
                    for argument_name, argument_spec in callable_action.arguments.items()
                    if argument_spec.required and argument_name not in route.match
                )
                if missing_arguments:
                    argument_list = ", ".join(missing_arguments)
                    raise ValueError(
                        f"Object `{item.object_id}` callable action `{action_name}` is missing argument value(s): "
                        f"{argument_list}."
                    )
                for argument_name, value in route.match.items():
                    argument_spec = callable_action.arguments[argument_name]
                    if value not in argument_spec.options:
                        raise ValueError(
                            f"Object `{item.object_id}` callable action `{action_name}` has unsupported value "
                            f"`{value}` for argument `{argument_name}`."
                        )
                route_signature = tuple(sorted(route.match.items()))
                if route_signature in seen_routes:
                    raise ValueError(
                        f"Object `{item.object_id}` callable action `{action_name}` defines duplicate route matches."
                    )
                seen_routes.add(route_signature)

            if not callable_action.arguments and len(callable_action.routes) != 1:
                raise ValueError(
                    f"Object `{item.object_id}` zero-argument callable action `{action_name}` must declare exactly one route."
                )
            if not callable_action.arguments and callable_action.routes[0].match:
                raise ValueError(
                    f"Object `{item.object_id}` zero-argument callable action `{action_name}` must use an empty route match."
                )
        return

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
        for action_name, callable_action in get_callable_action_definitions(world_object).items():
            for route in callable_action.routes:
                move_target = route.effect.move_to_location_id
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
            callable_actions = get_callable_action_definitions(world_object)
            for matcher in override.disabled_callable_actions:
                _validate_callable_action_matcher(
                    matcher,
                    callable_actions=callable_actions,
                    rule_id=rule.rule_id,
                    object_id=object_id,
                    label="disables",
                )
            for matcher in override.enabled_callable_actions:
                _validate_callable_action_matcher(
                    matcher,
                    callable_actions=callable_actions,
                    rule_id=rule.rule_id,
                    object_id=object_id,
                    label="enables",
                )
            for override_rule in override.callable_action_overrides:
                _validate_callable_action_matcher(
                    override_rule.match,
                    callable_actions=callable_actions,
                    rule_id=rule.rule_id,
                    object_id=object_id,
                    label="overrides",
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


def _validate_callable_action_matcher(
    matcher: CallableActionMatcher,
    *,
    callable_actions,
    rule_id: str,
    object_id: str,
    label: str,
) -> None:
    callable_action = callable_actions.get(matcher.action_name)
    if callable_action is None:
        raise ValueError(
            f"Dynamic rule `{rule_id}` {label} unknown callable action `{matcher.action_name}` on `{object_id}`."
        )

    unknown_arguments = sorted(set(matcher.action_args) - set(callable_action.arguments))
    if unknown_arguments:
        argument_list = ", ".join(unknown_arguments)
        raise ValueError(
            f"Dynamic rule `{rule_id}` matcher for `{object_id}` references unknown argument(s): {argument_list}."
        )
    if len(matcher.action_args) > 1:
        raise ValueError(
            f"Dynamic rule `{rule_id}` matcher for `{object_id}` may specify at most one action arg."
        )

    for argument_name, value in matcher.action_args.items():
        argument_spec = callable_action.arguments[argument_name]
        if value not in argument_spec.options:
            raise ValueError(
                f"Dynamic rule `{rule_id}` matcher for `{object_id}` has unsupported value "
                f"`{value}` for argument `{argument_name}`."
            )

    if not any(
        matches_callable_action_matcher(matcher.action_name, route.match, matcher)
        for route in callable_action.routes
    ):
        raise ValueError(
            f"Dynamic rule `{rule_id}` matcher for `{object_id}` does not match any callable action route."
        )
