from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from engine.rules import parse_time_label
from engine.state import (
    ActionCost,
    AgentState,
    Area,
    CallableActionDefinition,
    DynamicRule,
    Location,
    ObjectActionEffect,
    TerminationConfig,
    WorldEventRule,
    WorldObject,
)


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

    @field_validator("current_time")
    @classmethod
    def validate_current_time(cls, value: str) -> str:
        parse_time_label(value)
        return value.strip()


class ScenarioAreaSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)

    def to_area(self) -> Area:
        return Area(
            area_id=self.area_id,
            name=self.name,
            description=self.description,
            tags=list(self.tags),
        )


class ScenarioLocationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    name: str
    description: str
    area_id: str | None = None
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
            area_id=self.area_id,
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
    tags: list[str] = Field(default_factory=list)
    inspectable: bool = True
    readable: bool = False
    actionable: bool = False
    resource_content: str | None = None
    resource_file: str | None = None
    callable_actions: dict[str, CallableActionDefinition] = Field(default_factory=dict)

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
            tags=list(self.tags),
            inspectable=self.inspectable,
            readable=self.readable,
            actionable=self.actionable or bool(self.callable_actions),
            resource_content=resource_content,
            callable_actions={
                key: action.model_copy(deep=True)
                for key, action in self.callable_actions.items()
            },
        )


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    seed: int | None = None
    opening_briefing: str = ""
    public_rules: list[str] = Field(default_factory=list)
    initial_world_state: ScenarioInitialWorldState = Field(default_factory=ScenarioInitialWorldState)
    initial_agent_state: AgentState
    areas: list[ScenarioAreaSource] = Field(default_factory=list)
    locations: list[ScenarioLocationSource] = Field(default_factory=list)
    objects: list[ScenarioObjectSource] = Field(default_factory=list)
    action_costs: dict[str, ActionCost] = Field(default_factory=dict)
    dynamic_rules: list[DynamicRule] = Field(default_factory=list)
    event_rules: list[WorldEventRule] = Field(default_factory=list)
    termination_config: TerminationConfig = Field(default_factory=TerminationConfig)
