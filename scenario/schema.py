from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

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
    resource_content: Optional[str] = None
    resource_file: Optional[str] = None
    action_effects: dict[str, ObjectActionEffect] = Field(default_factory=dict)

    def to_world_object(self, *, resource_content: Optional[str]) -> WorldObject:
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
            action_effects={key: effect.model_copy(deep=True) for key, effect in self.action_effects.items()},
        )


class ScenarioSkillSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    file: str


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    seed: Optional[int] = None
    opening_briefing: str = ""
    public_rules: list[str] = Field(default_factory=list)
    initial_world_state: ScenarioInitialWorldState = Field(default_factory=ScenarioInitialWorldState)
    initial_agent_state: AgentState
    locations: list[ScenarioLocationSource] = Field(default_factory=list)
    objects: list[ScenarioObjectSource] = Field(default_factory=list)
    skills: list[ScenarioSkillSource] = Field(default_factory=list)
    action_costs: dict[str, ActionCost] = Field(default_factory=dict)
    event_rules: list[WorldEventRule] = Field(default_factory=list)
    termination_config: TerminationConfig = Field(default_factory=TerminationConfig)


ScenarioObjectSource.model_rebuild(_types_namespace={"ObjectActionEffect": ObjectActionEffect})
ScenarioConfig.model_rebuild(_types_namespace={"ObjectActionEffect": ObjectActionEffect})
