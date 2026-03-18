from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field

from engine.state import AgentState, Location, Skill, WorldObject, WorldState


class AgentObservation(BaseModel):
    location_id: str
    money: int
    energy: int
    inventory: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    status_effects: list[str] = Field(default_factory=list)


class LocationObservation(BaseModel):
    location_id: str
    name: str
    description: str
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ObjectObservation(BaseModel):
    object_id: str
    name: str
    object_type: str
    summary: str
    visible_state: dict[str, Any] = Field(default_factory=dict)
    action_ids: list[str] = Field(default_factory=list)


class SkillObservation(BaseModel):
    skill_id: str
    name: str
    description: str


class Observation(BaseModel):
    current_time: str
    agent: AgentObservation
    current_location: LocationObservation
    visible_objects: list[ObjectObservation] = Field(default_factory=list)
    visible_skills: list[SkillObservation] = Field(default_factory=list)


def _project_agent(agent: AgentState) -> AgentObservation:
    return AgentObservation(
        location_id=agent.location_id,
        money=agent.money,
        energy=agent.energy,
        inventory=dict(agent.inventory),
        notes=list(agent.notes),
        status_effects=list(agent.status_effects),
    )


def _project_location(location: Location) -> LocationObservation:
    return LocationObservation(
        location_id=location.location_id,
        name=location.name,
        description=location.description,
        links=list(location.links),
        tags=list(location.tags),
    )


def _project_object(world_object: WorldObject) -> ObjectObservation:
    return ObjectObservation(
        object_id=world_object.object_id,
        name=world_object.name,
        object_type=world_object.object_type,
        summary=world_object.summary,
        visible_state=deepcopy(world_object.visible_state),
        action_ids=list(world_object.action_ids),
    )


def _project_skill(skill: Skill) -> SkillObservation:
    return SkillObservation(skill_id=skill.skill_id, name=skill.name, description=skill.description)


def project_observation(state: WorldState) -> Observation:
    location = state.locations[state.agent.location_id]
    visible_objects = [
        _project_object(state.objects[object_id])
        for object_id in location.object_ids
        if object_id in state.objects and state.objects[object_id].location_id == location.location_id
    ]
    visible_skills = [_project_skill(skill) for skill in state.skills.values()]
    return Observation(
        current_time=state.current_time,
        agent=_project_agent(state.agent),
        current_location=_project_location(location),
        visible_objects=visible_objects,
        visible_skills=visible_skills,
    )


def summarize_observation(observation: Observation) -> dict[str, Any]:
    return {
        "current_time": observation.current_time,
        "location_id": observation.current_location.location_id,
        "visible_object_ids": [item.object_id for item in observation.visible_objects],
        "visible_skill_ids": [item.skill_id for item in observation.visible_skills],
        "note_count": len(observation.agent.notes),
    }
