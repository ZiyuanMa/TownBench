from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ScenarioInitialWorldState(BaseModel):
    current_time: str = "Day 1, 08:00"
    world_flags: dict[str, bool] = Field(default_factory=dict)


class ScenarioInitialAgentState(BaseModel):
    location_id: str
    money: int = 0
    energy: int = 100
    inventory: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    status_effects: list[str] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class ScenarioLocation(BaseModel):
    location_id: str
    name: str
    description: str
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ScenarioObjectActionEffect(BaseModel):
    message: str
    set_visible_state: dict[str, Any] = Field(default_factory=dict)
    set_world_flags: dict[str, bool] = Field(default_factory=dict)


class ScenarioObject(BaseModel):
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
    resource_file: Optional[str] = None
    action_effects: dict[str, ScenarioObjectActionEffect] = Field(default_factory=dict)


class ScenarioSkill(BaseModel):
    skill_id: str
    title: str
    file: str


class ScenarioActionCost(BaseModel):
    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = Field(default_factory=dict)


class ScenarioEventRule(BaseModel):
    event_id: str
    required_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_object_visible_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    trigger_once: bool = True


class ScenarioTerminationConfig(BaseModel):
    max_steps: Optional[int] = None
    stop_on_zero_energy: bool = True
    success_world_flags: list[str] = Field(default_factory=list)
    failure_world_flags: list[str] = Field(default_factory=list)


class ScenarioConfig(BaseModel):
    scenario_id: str
    seed: Optional[int] = None
    opening_briefing: str = ""
    public_rules: list[str] = Field(default_factory=list)
    initial_world_state: ScenarioInitialWorldState = Field(default_factory=ScenarioInitialWorldState)
    initial_agent_state: ScenarioInitialAgentState
    locations: list[ScenarioLocation] = Field(default_factory=list)
    objects: list[ScenarioObject] = Field(default_factory=list)
    skills: list[ScenarioSkill] = Field(default_factory=list)
    action_costs: dict[str, ScenarioActionCost] = Field(default_factory=dict)
    event_rules: list[ScenarioEventRule] = Field(default_factory=list)
    termination_config: ScenarioTerminationConfig = Field(default_factory=ScenarioTerminationConfig)
