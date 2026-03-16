from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from engine.state import ActionCost, AgentState, Location, ObjectActionEffect, TerminationConfig, WorldEventRule, WorldObject

class ScenarioInitialWorldState(BaseModel):
    current_time: str = "Day 1, 08:00"
    world_flags: dict[str, bool] = Field(default_factory=dict)


class ScenarioObjectSource(WorldObject):
    resource_file: Optional[str] = None


class ScenarioSkillSource(BaseModel):
    skill_id: str
    file: str


class ScenarioConfig(BaseModel):
    scenario_id: str
    seed: Optional[int] = None
    opening_briefing: str = ""
    public_rules: list[str] = Field(default_factory=list)
    initial_world_state: ScenarioInitialWorldState = Field(default_factory=ScenarioInitialWorldState)
    initial_agent_state: AgentState
    locations: list[Location] = Field(default_factory=list)
    objects: list[ScenarioObjectSource] = Field(default_factory=list)
    skills: list[ScenarioSkillSource] = Field(default_factory=list)
    action_costs: dict[str, ActionCost] = Field(default_factory=dict)
    event_rules: list[WorldEventRule] = Field(default_factory=list)
    termination_config: TerminationConfig = Field(default_factory=TerminationConfig)


ScenarioObjectSource.model_rebuild(_types_namespace={"ObjectActionEffect": ObjectActionEffect})
ScenarioConfig.model_rebuild(_types_namespace={"ObjectActionEffect": ObjectActionEffect})
