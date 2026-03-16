from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionCost(BaseModel):
    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = Field(default_factory=dict)


class WorldEventRule(BaseModel):
    event_id: str
    required_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_object_visible_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    trigger_once: bool = True


class TerminationConfig(BaseModel):
    max_steps: Optional[int] = None
    stop_on_zero_energy: bool = True
    success_world_flags: list[str] = Field(default_factory=list)
    failure_world_flags: list[str] = Field(default_factory=list)


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
    resource_content: Optional[str] = None
    action_effects: dict[str, "ObjectActionEffect"] = Field(default_factory=dict)


class ObjectActionEffect(BaseModel):
    message: str
    money_delta: int = 0
    set_visible_state: dict[str, Any] = Field(default_factory=dict)
    set_world_flags: dict[str, bool] = Field(default_factory=dict)


class Skill(BaseModel):
    skill_id: str
    name: str
    description: str
    content: str


class WorldState(BaseModel):
    current_time: str = "Day 1, 08:00"
    agent: AgentState
    locations: dict[str, Location]
    objects: dict[str, WorldObject] = Field(default_factory=dict)
    skills: dict[str, Skill] = Field(default_factory=dict)
    opening_briefing: str = ""
    public_rules: list[str] = Field(default_factory=list)
    world_flags: dict[str, bool] = Field(default_factory=dict)
    action_costs: dict[str, ActionCost] = Field(default_factory=dict)
    event_rules: list[WorldEventRule] = Field(default_factory=list)
    termination_config: TerminationConfig = Field(default_factory=TerminationConfig)
    triggered_event_ids: list[str] = Field(default_factory=list)
    scenario_id: str = "memory_scenario"
    seed: Optional[int] = None
