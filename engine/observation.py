from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field

from engine.callable_actions import build_callable_actions
from engine.dynamics import build_effective_object_view
from engine.rules import format_time_label
from engine.state import AgentState, Area, Location, WorldObject, WorldState


class AgentObservation(BaseModel):
    location_id: str
    money: int
    energy: int
    inventory: dict[str, int] = Field(default_factory=dict)
    status_effects: list[str] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class LocationObservation(BaseModel):
    location_id: str
    name: str
    description: str
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AreaObservation(BaseModel):
    area_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class CallableActionArgumentObservation(BaseModel):
    name: str
    type: str
    required: bool = True
    options: list[str] = Field(default_factory=list)
    description: str = ""


class CallableActionObservation(BaseModel):
    action_name: str
    description: str = ""
    arguments: list[CallableActionArgumentObservation] = Field(default_factory=list)
    signature_text: str


class ObjectObservation(BaseModel):
    object_id: str
    name: str
    object_type: str
    summary: str
    visible_state: dict[str, Any] = Field(default_factory=dict)
    callable_actions: list[CallableActionObservation] = Field(default_factory=list)


class Observation(BaseModel):
    current_time: str
    agent: AgentObservation
    current_location: LocationObservation
    current_area: AreaObservation | None = None
    nearby_locations: list[str] = Field(default_factory=list)
    visible_objects: list[ObjectObservation] = Field(default_factory=list)


def _project_agent(agent: AgentState) -> AgentObservation:
    return AgentObservation(
        location_id=agent.location_id,
        money=agent.money,
        energy=agent.energy,
        inventory=dict(agent.inventory),
        status_effects=list(agent.status_effects),
        stats=dict(agent.stats),
    )


def _project_location(location: Location) -> LocationObservation:
    return LocationObservation(
        location_id=location.location_id,
        name=location.name,
        description=location.description,
        links=list(location.links),
        tags=list(location.tags),
    )


def _project_area(area: Area) -> AreaObservation:
    return AreaObservation(
        area_id=area.area_id,
        name=area.name,
        description=area.description,
        tags=list(area.tags),
    )


def _project_object(world_object: WorldObject) -> ObjectObservation:
    callable_actions = [_project_callable_action(item) for item in build_callable_actions(world_object)]
    return ObjectObservation(
        object_id=world_object.object_id,
        name=world_object.name,
        object_type=world_object.object_type,
        summary=world_object.summary,
        visible_state=deepcopy(world_object.visible_state),
        callable_actions=deepcopy(callable_actions),
    )


def _project_effective_object(state: WorldState, object_id: str) -> ObjectObservation | None:
    effective_view = build_effective_object_view(state, object_id)
    if effective_view is None:
        return None
    return _project_object(effective_view.object)


def _project_callable_action(callable_action: dict[str, Any]) -> CallableActionObservation:
    arguments = [
        CallableActionArgumentObservation.model_validate(argument)
        for argument in callable_action.get("arguments", [])
    ]
    return CallableActionObservation(
        action_name=str(callable_action.get("action_name", "")).strip(),
        description=str(callable_action.get("description", "")),
        arguments=arguments,
        signature_text=_format_callable_action_signature(
            str(callable_action.get("action_name", "")).strip(),
            arguments,
        ),
    )


def _format_callable_action_signature(
    action_name: str,
    arguments: list[CallableActionArgumentObservation],
) -> str:
    if not arguments:
        return action_name
    formatted_arguments = [
        f"{argument.name}: {'|'.join(argument.options) if argument.options else 'none'}"
        for argument in arguments
    ]
    return f"{action_name}({', '.join(formatted_arguments)})"


def _build_nearby_locations(state: WorldState, current_location: Location) -> list[str]:
    nearby: set[str] = set(current_location.links)
    if current_location.area_id is not None:
        nearby.update(
            location.location_id
            for location in state.locations.values()
            if location.area_id == current_location.area_id
        )
    nearby.discard(current_location.location_id)
    return sorted(nearby)


def project_observation(state: WorldState) -> Observation:
    location = state.locations[state.agent.location_id]
    current_area = None
    if location.area_id is not None and location.area_id in state.areas:
        current_area = _project_area(state.areas[location.area_id])
    visible_objects = [
        projected
        for object_id in location.object_ids
        if object_id in state.objects and state.objects[object_id].location_id == location.location_id
        for projected in [_project_effective_object(state, object_id)]
        if projected is not None
    ]
    return Observation(
        current_time=format_time_label(state.current_time),
        agent=_project_agent(state.agent),
        current_location=_project_location(location),
        current_area=current_area,
        nearby_locations=_build_nearby_locations(state, location),
        visible_objects=visible_objects,
    )


def summarize_observation(observation: Observation) -> dict[str, Any]:
    return {
        "current_time": observation.current_time,
        "location_id": observation.current_location.location_id,
        "current_area_id": observation.current_area.area_id if observation.current_area is not None else None,
        "nearby_location_ids": list(observation.nearby_locations),
        "visible_object_ids": [item.object_id for item in observation.visible_objects],
    }
