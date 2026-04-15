from __future__ import annotations

from typing import Any

from engine.action_models import Action
from engine.actions import normalize_action
from engine.observation import Observation
from engine.results import StepResult


def render_tool_result(
    action: Action | dict[str, Any],
    result: StepResult,
) -> str:
    normalized_action = normalize_action(action)
    return _render_text_tool_result(normalized_action, result)


def render_initial_observation(
    observation: Observation | dict[str, Any],
) -> str:
    normalized = _normalize_observation(observation)
    agent = normalized.agent
    location = normalized.current_location
    lines = [
        f"Current time: {normalized.current_time}",
        f"Current location: {location.name} ({location.location_id})",
        f"Location description: {location.description}",
    ]
    if normalized.current_area is not None:
        lines.extend(
            [
                f"Current area: {normalized.current_area.name} ({normalized.current_area.area_id})",
                f"Area description: {normalized.current_area.description}",
            ]
        )
    if normalized.nearby_locations:
        lines.append(f"Nearby locations: {', '.join(normalized.nearby_locations)}")

    lines.extend(
        [
            f"Money: {agent.money}",
            f"Energy: {agent.energy}",
        ]
    )
    if agent.inventory:
        lines.append(f"Inventory: {_format_mapping(agent.inventory)}")
    if agent.status_effects:
        lines.append(f"Status effects: {', '.join(agent.status_effects)}")
    if agent.stats:
        lines.append(f"Stats: {_format_mapping(agent.stats)}")

    if normalized.visible_objects:
        lines.append("Visible objects:")
        for item in normalized.visible_objects:
            line = f"- {item.name} ({item.object_id}): {item.summary}"
            if item.action_ids:
                line += f" Actions: {', '.join(item.action_ids)}."
            if item.visible_state:
                line += f" Visible state: {_format_mapping(item.visible_state)}."
            lines.append(line)

    if normalized.visible_skills:
        lines.append("Visible skills:")
        for item in normalized.visible_skills:
            lines.append(f"- {item.name} ({item.skill_id}): {item.description}")

    return "\n".join(lines)


def _render_text_tool_result(action: Action, result: StepResult) -> str:
    sections = [result.message]
    if result.success:
        details = _render_success_details(action, result.data)
    else:
        details = _render_failure_sections(action, result)

    if details:
        sections.extend(details)

    delta_line = _render_delta_line(result)
    if delta_line:
        sections.append(delta_line)
    if _should_render_observation_snapshot(action, result):
        sections.extend(_render_observation_snapshot(result.observation))
    return "\n".join(sections)


def _render_success_details(action: Action, data: dict[str, Any]) -> list[str]:
    if action.type == "check_status":
        status = data.get("agent_status", {})
        details = [
            f"Current time: {status.get('current_time', '')}",
            f"Location: {status.get('location_id', '')}",
            f"Money: {status.get('money', 0)}",
            f"Energy: {status.get('energy', 0)}",
        ]
        if status.get("inventory"):
            details.append(f"Inventory: {_format_mapping(status['inventory'])}")
        if status.get("status_effects"):
            details.append(f"Status effects: {', '.join(status['status_effects'])}")
        if status.get("stats"):
            details.append(f"Stats: {_format_mapping(status['stats'])}")
        return details

    if action.type == "inspect":
        if data.get("kind") == "location":
            location = data.get("location", {})
            details = [
                f"Location id: {location.get('location_id', '')}",
                f"Description: {location.get('description', '')}",
            ]
            if location.get("links"):
                details.append(f"Links: {', '.join(location['links'])}")
            return details
        if data.get("kind") == "object":
            obj = data.get("object", {})
            details = [
                f"Object id: {obj.get('object_id', '')}",
                f"Summary: {obj.get('summary', '')}",
            ]
            if obj.get("action_ids"):
                details.append(f"Available actions: {', '.join(obj['action_ids'])}")
            if obj.get("visible_state"):
                details.append(f"Visible state: {_format_mapping(obj['visible_state'])}")
            return details

    if action.type == "open_resource":
        return [f"Title: {data.get('title', '')}", "Content:", str(data.get("content", ""))]

    if action.type == "load_skill":
        return [
            f"Skill id: {data.get('skill_id', '')}",
            f"Description: {data.get('description', '')}",
            "Content:",
            str(data.get("content", "")),
        ]

    if action.type == "call_action":
        details = []
        if data.get("action"):
            details.append(f"Action: {data['action']}")
        if data.get("location_id"):
            details.append(f"Current location: {data['location_id']}")
        if data.get("visible_state"):
            details.append(f"Visible state: {_format_mapping(data['visible_state'])}")
        return details

    return []


def _render_failure_sections(action: Action, result: StepResult) -> list[str]:
    summary = _build_failure_summary(result)
    next_steps = _build_failure_next_steps(action, result)
    context = _render_failure_context(action, result.data)

    sections: list[str] = []
    if summary:
        sections.append(f"Hint: {summary}")
    if next_steps:
        sections.append("What to try next:")
        sections.extend(f"- {step}" for step in next_steps)
    if context:
        sections.append("Context:")
        sections.extend(f"- {detail}" for detail in context)
    return sections


def _build_failure_summary(result: StepResult) -> str | None:
    error_type = _resolve_error_type(result)
    data = result.data

    if error_type == "missing_target":
        return "This tool call is missing the target id it needs."
    if error_type == "missing_action_name":
        return "This action call is missing the action name."
    if error_type in {"unknown_target", "unknown_skill", "unknown_location"}:
        return "The id you provided is not recognized in the current environment."
    if error_type == "unreachable_location":
        return "You cannot move directly to that location from where you are now."
    if error_type == "not_accessible":
        return "The target exists, but it is not in your current location."
    if error_type == "not_actionable":
        return "The target object does not support callable actions."
    if error_type == "not_inspectable":
        return "The target cannot be inspected."
    if error_type == "not_readable":
        return "The target is not a readable resource."
    if error_type == "action_not_exposed":
        return "That action is not currently exposed on the target object."
    if error_type == "action_temporarily_unavailable":
        return "That action exists on the target, but it is temporarily unavailable right now."
    if error_type == "missing_inventory":
        return "You do not currently have the inventory items this action requires."
    if error_type == "insufficient_money":
        return "You do not have enough money for this action."
    if error_type == "inventory_capacity_exceeded":
        return "This step would exceed the current carry limit."
    if error_type == "invalid_action":
        return "The action payload could not be parsed into a valid TownBench action."
    if error_type == "not_implemented":
        return "The environment does not implement that action type."
    if error_type == "episode_done":
        return "The episode has already finished, so additional actions will not change the state."
    if error_type != "missing_prerequisites":
        return None
    if data.get("required_agent_stats"):
        return "Your current stats do not satisfy this action's requirement yet."
    if data.get("required_world_flags"):
        return "This action depends on prior progress that has not been completed yet."
    return "This action's prerequisites are not currently satisfied."


def _build_failure_next_steps(action: Action, result: StepResult) -> list[str]:
    error_type = _resolve_error_type(result)
    data = result.data

    if error_type == "missing_target":
        if action.type == "move_to" and "reachable_locations" in data:
            return _take_steps(
                f"Retry with one of the currently reachable locations: {_format_list(data.get('reachable_locations', []))}.",
            )
        if action.type == "load_skill" and "visible_skill_ids" in data:
            return _take_steps(
                f"Retry with one of the visible skill ids: {_format_list(data.get('visible_skill_ids', []))}.",
            )
        if "visible_object_ids" in data:
            return _take_steps(
                "Retry with a valid target_id from the current room.",
                f"Visible objects now: {_format_list(data.get('visible_object_ids', []))}.",
            )
        return _take_steps("Retry with a valid target_id.")

    if error_type == "missing_action_name":
        return _take_steps(
            "Provide an action_name when calling call_action.",
            "Inspect the target first if you need to see which actions are currently exposed.",
        )

    if error_type == "unknown_skill":
        return _take_steps(
            f"Use one of the visible skill ids instead: {_format_list(data.get('visible_skill_ids', []))}.",
        )

    if error_type in {"unknown_location", "unreachable_location"}:
        return _take_steps(
            f"Move to one of the locations that is currently reachable: {_format_list(data.get('reachable_locations', []))}.",
            "Use the town map and your current location to plan a valid route.",
        )

    if error_type == "unknown_target":
        return _take_steps(
            f"Use one of the objects that is currently visible: {_format_list(data.get('visible_object_ids', []))}.",
            "Inspect the room again if you need to confirm what is present.",
        )

    if error_type == "not_accessible":
        return _take_steps(
            "Move through nearby locations until the target becomes visible in your current room.",
            f"Use only objects that are visible right now: {_format_list(data.get('visible_object_ids', []))}.",
        )

    if error_type in {"not_actionable", "not_inspectable", "not_readable"}:
        return _take_steps(
            "Use a tool that matches what this target actually supports.",
            "Inspect the room or object again before retrying a different tool call.",
        )

    if error_type == "action_not_exposed":
        return _take_steps(
            f"Use one of the actions currently exposed on the target: {_format_list(data.get('available_actions', []))}.",
            "Inspect the object again if you need more context before choosing an action.",
        )

    if error_type == "action_temporarily_unavailable":
        return _take_steps(
            "Check the current time and the object's visible state before retrying.",
            "Do other useful work first and come back after the environment state changes.",
        )

    if error_type == "missing_inventory":
        return _take_steps(
            f"Obtain the required inventory before retrying: {_format_mapping_or_none(data.get('required_inventory', {}))}.",
            "Look for shops, storage, or preparation actions that can supply the missing items.",
        )

    if error_type == "insufficient_money":
        return _take_steps(
            "Earn more money before retrying this action.",
            "Prioritize actions that generate cash or reduce spending first.",
        )

    if error_type == "inventory_capacity_exceeded":
        return _take_steps(
            "Free inventory space before retrying this step.",
            "If the scenario supports it, increase carry_limit before taking on more items.",
        )

    if error_type == "invalid_action":
        return _take_steps("Retry with a valid TownBench tool call and the required arguments.")

    if error_type == "not_implemented":
        return _take_steps("Use one of the supported TownBench tools instead of retrying this action type.")

    if error_type == "episode_done":
        return []

    if data.get("required_agent_stats"):
        return _take_steps(
            f"Reach the required stats before retrying: {_format_mapping_or_none(data.get('required_agent_stats', {}))}.",
            "Use other actions that can improve your agent stats first.",
        )
    if data.get("required_world_flags"):
        return _take_steps(
            "Inspect the target to review what is currently exposed.",
            "Explore nearby locations for prerequisite tasks or state changes.",
            "Avoid repeating the same action until new progress has been made.",
        )
    return _take_steps("Change the environment state before retrying the same action.")


def _render_failure_context(action: Action, data: dict[str, Any]) -> list[str]:
    details: list[str] = []
    target_id = data.get("target_id") or action.target_id
    requested_action = data.get("requested_action") or action.args.get("action")

    if target_id:
        details.append(f"Requested target: {target_id}")
    if requested_action:
        details.append(f"Requested action: {requested_action}")
    if data.get("current_location_id"):
        details.append(f"Current location: {data['current_location_id']}")
    if data.get("current_time"):
        details.append(f"Current time: {data['current_time']}")
    if "reachable_locations" in data:
        details.append(f"Reachable locations now: {_format_list(data.get('reachable_locations', []))}")
    if "visible_object_ids" in data:
        details.append(f"Visible objects now: {_format_list(data.get('visible_object_ids', []))}")
    if "visible_skill_ids" in data:
        details.append(f"Visible skills now: {_format_list(data.get('visible_skill_ids', []))}")
    if "available_actions" in data:
        details.append(f"Available actions on target: {_format_list(data.get('available_actions', []))}")
    if data.get("visible_state"):
        details.append(f"Visible state now: {_format_mapping(data['visible_state'])}")
    if data.get("required_inventory"):
        details.append(f"Required inventory: {_format_mapping(data['required_inventory'])}")
    if "current_inventory" in data:
        details.append(f"Current inventory: {_format_mapping_or_none(data.get('current_inventory', {}))}")
    if "required_money" in data:
        details.append(f"Required money: {data['required_money']}")
    if "current_money" in data:
        details.append(f"Current money: {data['current_money']}")
    if data.get("required_agent_stats"):
        details.append(f"Required stats: {_format_mapping(data['required_agent_stats'])}")
    if "current_agent_stats" in data:
        details.append(f"Current stats: {_format_mapping_or_none(data.get('current_agent_stats', {}))}")
    if data.get("referenced_location_id"):
        details.append(f"Referenced location: {data['referenced_location_id']}")
    return details


def _resolve_error_type(result: StepResult) -> str:
    raw = result.data.get("error_type")
    if isinstance(raw, str) and raw:
        return raw
    if result.warnings:
        return str(result.warnings[0])
    return ""


def _take_steps(*steps: str) -> list[str]:
    unique_steps: list[str] = []
    for step in steps:
        normalized = step.strip()
        if not normalized or normalized in unique_steps or normalized.endswith("none."):
            continue
        unique_steps.append(normalized)
    return unique_steps[:3]


def _render_delta_line(result: StepResult) -> str | None:
    parts = []
    if result.time_delta:
        parts.append(f"time {result.time_delta:+d}")
    if result.money_delta:
        parts.append(f"money {result.money_delta:+d}")
    if result.energy_delta:
        parts.append(f"energy {result.energy_delta:+d}")
    if result.inventory_delta:
        parts.append(f"inventory {_format_mapping(result.inventory_delta)}")
    if not parts:
        return None
    return "Effects: " + ", ".join(parts)


def _should_render_observation_snapshot(action: Action, result: StepResult) -> bool:
    if not result.success:
        return False
    return action.type in {"move_to", "call_action"}


def _render_observation_snapshot(observation: Observation) -> list[str]:
    agent = observation.agent
    location = observation.current_location
    lines = [
        "Current snapshot:",
        f"Time: {observation.current_time}",
        f"Location: {location.name} ({location.location_id})",
    ]
    if observation.nearby_locations:
        lines.append(f"Nearby: {', '.join(observation.nearby_locations)}")
    lines.append(f"Money: {agent.money}")
    lines.append(f"Energy: {agent.energy}")
    inventory = agent.inventory
    if inventory:
        lines.append(f"Inventory: {_format_mapping(inventory)}")
    stats = agent.stats
    if stats:
        lines.append(f"Stats: {_format_mapping(stats)}")

    if observation.visible_objects:
        lines.append("Visible objects:")
        for item in observation.visible_objects:
            object_line = f"- {item.name} ({item.object_id})"
            if item.action_ids:
                object_line += f" Actions: {', '.join(item.action_ids)}."
            visible_state = item.visible_state
            if visible_state:
                object_line += f" Visible state: {_format_mapping(visible_state)}."
            lines.append(object_line)

    if observation.visible_skills:
        lines.append("Visible skills:")
        for item in observation.visible_skills:
            lines.append(f"- {item.name} ({item.skill_id})")
    return lines


def _format_mapping(values: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items())


def _format_mapping_or_none(values: dict[str, Any]) -> str:
    if not values:
        return "none"
    return _format_mapping(values)


def _format_list(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


def _normalize_observation(observation: Observation | dict[str, Any]) -> Observation:
    if isinstance(observation, Observation):
        return observation
    return Observation.model_validate(observation)
