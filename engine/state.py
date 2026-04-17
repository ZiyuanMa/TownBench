from __future__ import annotations

import re
from typing import Any, Literal

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


class CallableActionMatcher(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_name: str
    action_args: dict[str, str] = Field(default_factory=dict)


class CallableActionOverrideRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: CallableActionMatcher
    override: ActionEffectOverride


class ObjectDynamicOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible_state: dict[str, Any] = Field(default_factory=dict)
    disabled_callable_actions: list[CallableActionMatcher] = Field(default_factory=list)
    enabled_callable_actions: list[CallableActionMatcher] = Field(default_factory=list)
    callable_action_overrides: list[CallableActionOverrideRule] = Field(default_factory=list)


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
    callable_actions: dict[str, "CallableActionDefinition"] = Field(default_factory=dict)


class CallableActionArgumentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["enum"] = "enum"
    required: bool = True
    options: list[str] = Field(default_factory=list)
    description: str = ""


class CallableActionRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: dict[str, str] = Field(default_factory=dict)
    effect: "ObjectActionEffect"


class CallableActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = ""
    arguments: dict[str, CallableActionArgumentSpec] = Field(default_factory=dict)
    routes: list[CallableActionRoute] = Field(default_factory=list)


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
    current_time: int = 8 * 60
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
