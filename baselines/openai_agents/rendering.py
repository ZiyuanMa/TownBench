from __future__ import annotations

import json
from typing import Any, Literal

from engine.action_models import Action
from engine.actions import normalize_action
from engine.observation import Observation
from engine.results import StepResult

RenderMode = Literal["text", "json"]


def render_tool_result(
    action: Action | dict[str, Any],
    result: StepResult,
    *,
    mode: RenderMode = "text",
) -> str | dict[str, Any]:
    if mode == "json":
        return result.model_dump()

    normalized_action = normalize_action(action)
    return _render_text_tool_result(normalized_action, result)


def render_initial_observation(
    observation: Observation | dict[str, Any],
    *,
    mode: RenderMode = "text",
) -> str:
    if mode == "json":
        return json.dumps(_normalize_observation(observation).model_dump(), ensure_ascii=False, indent=2)

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
    data = result.data
    sections = [result.message]
    if result.success:
        details = _render_success_details(action, data)
    else:
        details = _render_failure_details(action, data)

    if details:
        sections.extend(details)

    delta_line = _render_delta_line(result)
    if delta_line:
        sections.append(delta_line)
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
            details = [f"Location id: {location.get('location_id', '')}", f"Description: {location.get('description', '')}"]
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


def _render_failure_details(action: Action, data: dict[str, Any]) -> list[str]:
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
    if data.get("reachable_locations"):
        details.append(f"Reachable locations now: {', '.join(data['reachable_locations'])}")
    if data.get("visible_object_ids"):
        details.append(f"Visible objects now: {', '.join(data['visible_object_ids'])}")
    if data.get("visible_skill_ids"):
        details.append(f"Visible skills now: {', '.join(data['visible_skill_ids'])}")
    if data.get("available_actions"):
        details.append(f"Available actions on target: {', '.join(data['available_actions'])}")
    if data.get("dynamic_reason"):
        details.append(f"Dynamic reason: {data['dynamic_reason']}")
    if data.get("visible_state"):
        details.append(f"Visible state now: {_format_mapping(data['visible_state'])}")
    if data.get("required_inventory"):
        details.append(f"Required inventory: {_format_mapping(data['required_inventory'])}")
    if data.get("current_inventory"):
        details.append(f"Current inventory: {_format_mapping(data['current_inventory'])}")
    if "required_money" in data:
        details.append(f"Required money: {data['required_money']}")
    if "current_money" in data:
        details.append(f"Current money: {data['current_money']}")
    if data.get("required_world_flags"):
        details.append(f"Required world flags: {_format_mapping(data['required_world_flags'])}")
    if data.get("required_agent_stats"):
        details.append(f"Required stats: {_format_mapping(data['required_agent_stats'])}")
    if data.get("current_agent_stats"):
        details.append(f"Current stats: {_format_mapping(data['current_agent_stats'])}")
    if data.get("referenced_location_id"):
        details.append(f"Referenced location: {data['referenced_location_id']}")
    return details


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


def _format_mapping(values: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items())


def _normalize_observation(observation: Observation | dict[str, Any]) -> Observation:
    if isinstance(observation, Observation):
        return observation
    return Observation.model_validate(observation)
