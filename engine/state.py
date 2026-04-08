from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

CLOCK_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


class ActionCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = Field(default_factory=dict)


class WorldEventRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    required_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_object_visible_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    trigger_once: bool = True


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_clock_time(cls, value: str) -> str:
        normalized = value.strip()
        if CLOCK_TIME_PATTERN.match(normalized) is None:
            raise ValueError(f"Unsupported clock time format: `{value}`.")
        hour, minute = (int(part) for part in normalized.split(":"))
        if hour >= 24 or minute >= 60:
            raise ValueError(f"Unsupported clock time format: `{value}`.")
        return normalized


class DynamicCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_window: TimeWindow


class ActionEffectOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    money_delta: int | None = None
    energy_delta: int | None = None
    inventory_delta: dict[str, int] | None = None
    required_inventory: dict[str, int] | None = None
    required_agent_stats: dict[str, int] | None = None
    required_money: int | None = None
    set_visible_state: dict[str, Any] | None = None
    set_world_flags: dict[str, bool] | None = None


class ObjectDynamicOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible_state: dict[str, Any] = Field(default_factory=dict)
    disabled_actions: list[str] = Field(default_factory=list)
    enabled_actions: list[str] = Field(default_factory=list)
    action_overrides: dict[str, ActionEffectOverride] = Field(default_factory=dict)


class DynamicRuleApplication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_overrides: dict[str, ObjectDynamicOverride] = Field(default_factory=dict)


class DynamicRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    priority: int = 0
    when: DynamicCondition
    apply: DynamicRuleApplication = Field(default_factory=DynamicRuleApplication)


class TerminationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int | None = None
    stop_on_zero_energy: bool = True
    success_world_flags: list[str] = Field(default_factory=list)
    failure_world_flags: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    money: int = 0
    energy: int = 100
    inventory: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    status_effects: list[str] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class Area(BaseModel):
    area_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class Location(BaseModel):
    location_id: str
    name: str
    description: str
    area_id: str | None = None
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
    resource_content: str | None = None
    action_effects: dict[str, "ObjectActionEffect"] = Field(default_factory=dict)


class ObjectActionEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = Field(default_factory=dict)
    required_world_flags: dict[str, bool] = Field(default_factory=dict)
    required_inventory: dict[str, int] = Field(default_factory=dict)
    required_agent_stats: dict[str, int] = Field(default_factory=dict)
    required_money: int = 0
    agent_stat_deltas: dict[str, int] = Field(default_factory=dict)
    set_visible_state: dict[str, Any] = Field(default_factory=dict)
    set_world_flags: dict[str, bool] = Field(default_factory=dict)
    move_to_location_id: str | None = None


class Skill(BaseModel):
    skill_id: str
    name: str
    description: str
    content: str


class WorldState(BaseModel):
    current_time: str = "Day 1, 08:00"
    agent: AgentState
    areas: dict[str, Area] = Field(default_factory=dict)
    locations: dict[str, Location]
    objects: dict[str, WorldObject] = Field(default_factory=dict)
    skills: dict[str, Skill] = Field(default_factory=dict)
    opening_briefing: str = ""
    public_rules: list[str] = Field(default_factory=list)
    world_flags: dict[str, bool] = Field(default_factory=dict)
    action_costs: dict[str, ActionCost] = Field(default_factory=dict)
    dynamic_rules: list[DynamicRule] = Field(default_factory=list)
    event_rules: list[WorldEventRule] = Field(default_factory=list)
    termination_config: TerminationConfig = Field(default_factory=TerminationConfig)
    active_event_ids: list[str] = Field(default_factory=list)
    triggered_event_ids: list[str] = Field(default_factory=list)
    scenario_id: str = "memory_scenario"
    seed: int | None = None
