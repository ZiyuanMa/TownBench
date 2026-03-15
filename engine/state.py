from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    location_id: str
    money: int = 0
    energy: int = 100
    inventory: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    status_effects: list[str] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class Location(BaseModel):
    location_id: str
    name: str
    description: str
    links: list[str] = Field(default_factory=list)
    object_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class WorldObject(BaseModel):
    object_id: str
    name: str
    object_type: str
    location_id: str
    summary: str
    visible_state: dict[str, Any] = Field(default_factory=dict)
    action_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    inspectable: bool = True
    readable: bool = False
    actionable: bool = False


class Skill(BaseModel):
    skill_id: str
    title: str
    content: str


class WorldState(BaseModel):
    current_time: str = "Day 1, 08:00"
    agent: AgentState
    locations: dict[str, Location]
    objects: dict[str, WorldObject] = Field(default_factory=dict)
    skills: dict[str, Skill] = Field(default_factory=dict)
    world_flags: dict[str, bool] = Field(default_factory=dict)
    scenario_id: str = "memory_scenario"
    seed: Optional[int] = None
