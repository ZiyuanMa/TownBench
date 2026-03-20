from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.state import ActionCost, AgentState, Location, ObjectActionEffect, TerminationConfig, WorldEventRule, WorldObject


def _reject_runtime_only_field(data: Any, *, field_name: str, label: str, id_key: str) -> Any:
    if isinstance(data, dict) and field_name in data:
        item_id = data.get(id_key, "<unknown>")
        raise ValueError(
            f"{label} `{item_id}` must not declare `{field_name}`; it is derived during scenario loading."
        )
    return data


class ScenarioInitialWorldState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_time: str = "Day 1, 08:00"
    world_flags: dict[str, bool] = Field(default_factory=dict)


class ScenarioAgentStateSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    money: int = 0
    energy: int = 100
    inventory: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    status_effects: list[str] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)

    def to_agent_state(self) -> AgentState:
        return AgentState(
            location_id=self.location_id,
            money=self.money,
            energy=self.energy,
            inventory=dict(self.inventory),
            notes=list(self.notes),
            status_effects=list(self.status_effects),
            stats=dict(self.stats),
        )


class ScenarioLocationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    name: str
    description: str
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def reject_object_ids(cls, data: Any) -> Any:
        return _reject_runtime_only_field(
            data,
            field_name="object_ids",
            label="Location",
            id_key="location_id",
        )

    def to_location(self) -> Location:
        return Location(
            location_id=self.location_id,
            name=self.name,
            description=self.description,
            links=list(self.links),
            object_ids=[],
            tags=list(self.tags),
        )


class ScenarioObjectSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    resource_file: str | None = None
    action_effects: dict[str, "ScenarioObjectActionEffectSource"] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_resource_source(self) -> "ScenarioObjectSource":
        if self.resource_content is not None and self.resource_file is not None:
            raise ValueError(
                f"Object `{self.object_id}` must define only one of `resource_content` or `resource_file`."
            )
        return self

    def to_world_object(self, *, resource_content: str | None) -> WorldObject:
        return WorldObject(
            object_id=self.object_id,
            name=self.name,
            object_type=self.object_type,
            location_id=self.location_id,
            summary=self.summary,
            visible_state=deepcopy(self.visible_state),
            action_ids=list(self.action_ids),
            tags=list(self.tags),
            inspectable=self.inspectable,
            readable=self.readable,
            actionable=self.actionable or bool(self.action_effects),
            resource_content=resource_content,
            action_effects={key: effect.to_action_effect() for key, effect in self.action_effects.items()},
        )


class ScenarioActionCostSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_delta: int = 0
    money_delta: int = 0
    energy_delta: int = 0
    inventory_delta: dict[str, int] = Field(default_factory=dict)

    def to_action_cost(self) -> ActionCost:
        return ActionCost(
            time_delta=self.time_delta,
            money_delta=self.money_delta,
            energy_delta=self.energy_delta,
            inventory_delta=dict(self.inventory_delta),
        )


class ScenarioObjectActionEffectSource(BaseModel):
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

    def to_action_effect(self) -> ObjectActionEffect:
        return ObjectActionEffect(
            message=self.message,
            money_delta=self.money_delta,
            energy_delta=self.energy_delta,
            inventory_delta=dict(self.inventory_delta),
            required_world_flags=dict(self.required_world_flags),
            required_inventory=dict(self.required_inventory),
            required_agent_stats=dict(self.required_agent_stats),
            required_money=self.required_money,
            agent_stat_deltas=dict(self.agent_stat_deltas),
            set_visible_state=deepcopy(self.set_visible_state),
            set_world_flags=dict(self.set_world_flags),
            move_to_location_id=self.move_to_location_id,
        )


class ScenarioSkillSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    file: str


class ScenarioEventRuleSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    required_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_object_visible_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    trigger_once: bool = True

    def to_event_rule(self) -> WorldEventRule:
        return WorldEventRule(
            event_id=self.event_id,
            required_world_flags=dict(self.required_world_flags),
            set_world_flags=dict(self.set_world_flags),
            set_object_visible_state=deepcopy(self.set_object_visible_state),
            trigger_once=self.trigger_once,
        )


class ScenarioTerminationConfigSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int | None = None
    stop_on_zero_energy: bool = True
    success_world_flags: list[str] = Field(default_factory=list)
    failure_world_flags: list[str] = Field(default_factory=list)

    def to_termination_config(self) -> TerminationConfig:
        return TerminationConfig(
            max_steps=self.max_steps,
            stop_on_zero_energy=self.stop_on_zero_energy,
            success_world_flags=list(self.success_world_flags),
            failure_world_flags=list(self.failure_world_flags),
        )


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    seed: int | None = None
    opening_briefing: str = ""
    public_rules: list[str] = Field(default_factory=list)
    initial_world_state: ScenarioInitialWorldState = Field(default_factory=ScenarioInitialWorldState)
    initial_agent_state: ScenarioAgentStateSource
    locations: list[ScenarioLocationSource] = Field(default_factory=list)
    objects: list[ScenarioObjectSource] = Field(default_factory=list)
    skills: list[ScenarioSkillSource] = Field(default_factory=list)
    action_costs: dict[str, ScenarioActionCostSource] = Field(default_factory=dict)
    event_rules: list[ScenarioEventRuleSource] = Field(default_factory=list)
    termination_config: ScenarioTerminationConfigSource = Field(default_factory=ScenarioTerminationConfigSource)


ScenarioObjectSource.model_rebuild(_types_namespace={"ScenarioObjectActionEffectSource": ScenarioObjectActionEffectSource})
