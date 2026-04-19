from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    when: "ConditionNode" = Field(default_factory=lambda: ConditionNode(kind="world_flags"))
    set_world_flags: dict[str, bool] = Field(default_factory=dict)
    set_object_visible_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    trigger_once: bool = True

    @model_validator(mode="before")
    @classmethod
    def migrate_required_world_flags(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "required_world_flags" not in data:
            return data
        if "when" in data:
            raise ValueError("WorldEventRule must not declare both `when` and `required_world_flags`.")
        migrated = dict(data)
        migrated["when"] = {"world_flags": migrated.pop("required_world_flags")}
        return migrated


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


ConditionKind = Literal[
    "all",
    "any",
    "not",
    "time_window",
    "world_flags",
    "location_id",
    "has_inventory",
    "money_at_least",
    "energy_at_least",
]


class ConditionNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ConditionKind
    children: list["ConditionNode"] = Field(default_factory=list)
    time_window: TimeWindow | None = None
    world_flags: dict[str, bool] | None = None
    location_id: str | None = None
    has_inventory: dict[str, int] | None = None
    threshold: int | None = None

    _ALLOWED_PAYLOADS_BY_KIND: dict[str, set[str]] = {
        "all": set(),
        "any": set(),
        "not": set(),
        "time_window": {"time_window"},
        "world_flags": {"world_flags"},
        "location_id": {"location_id"},
        "has_inventory": {"has_inventory"},
        "money_at_least": {"threshold"},
        "energy_at_least": {"threshold"},
    }

    @model_validator(mode="before")
    @classmethod
    def normalize_authored_condition(cls, data: Any) -> Any:
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            raise ValueError("Condition nodes must be mappings.")
        if "kind" in data:
            return data
        if len(data) != 1:
            raise ValueError("Condition nodes must declare exactly one key.")

        key, payload = next(iter(data.items()))
        if key in {"all", "any"}:
            if not isinstance(payload, list):
                raise ValueError(f"Condition node `{key}` must wrap a list.")
            return {"kind": key, "children": payload}
        if key == "not":
            if isinstance(payload, list):
                raise ValueError("Condition node `not` must wrap exactly one child node.")
            return {"kind": key, "children": [payload]}
        if key == "time_window":
            return {"kind": key, "time_window": payload}
        if key == "world_flags":
            return {"kind": key, "world_flags": payload}
        if key == "location_id":
            return {"kind": key, "location_id": payload}
        if key == "has_inventory":
            return {"kind": key, "has_inventory": payload}
        if key in {"money_at_least", "energy_at_least"}:
            return {"kind": key, "threshold": payload}
        raise ValueError(f"Unsupported condition node `{key}`.")

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, value: int | None) -> int | None:
        if value is not None and isinstance(value, bool):
            raise ValueError("Condition thresholds must be integers, not booleans.")
        return value

    @field_validator("location_id")
    @classmethod
    def validate_location_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Condition `location_id` must be a non-empty string.")
        return normalized

    @field_validator("has_inventory")
    @classmethod
    def validate_has_inventory(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return value
        normalized: dict[str, int] = {}
        for item_id, quantity in value.items():
            if isinstance(quantity, bool):
                raise ValueError("Condition `has_inventory` quantities must be integers, not booleans.")
            if quantity < 0:
                raise ValueError("Condition `has_inventory` quantities must be non-negative.")
            normalized[item_id] = quantity
        return normalized

    def _present_payload_fields(self) -> set[str]:
        present: set[str] = set()
        if self.time_window is not None:
            present.add("time_window")
        if self.world_flags is not None:
            present.add("world_flags")
        if self.location_id is not None:
            present.add("location_id")
        if self.has_inventory is not None:
            present.add("has_inventory")
        if self.threshold is not None:
            present.add("threshold")
        return present

    def _missing_required_payloads(self) -> set[str]:
        if self.kind == "time_window" and self.time_window is None:
            return {"time_window"}
        if self.kind == "location_id" and self.location_id is None:
            return {"location_id"}
        if self.kind in {"money_at_least", "energy_at_least"} and self.threshold is None:
            return {"threshold"}
        return set()

    @model_validator(mode="after")
    def validate_shape(self) -> "ConditionNode":
        if self.kind == "not":
            if len(self.children) != 1:
                raise ValueError("Condition node `not` must wrap exactly one child node.")
        elif self.kind in {"all", "any"}:
            pass
        else:
            if self.children:
                raise ValueError(f"Atomic condition node `{self.kind}` must not declare children.")

        allowed_payloads = self._ALLOWED_PAYLOADS_BY_KIND.get(self.kind)
        if allowed_payloads is None:
            raise ValueError(f"Unsupported condition node kind `{self.kind}`.")

        present_payloads = self._present_payload_fields()
        extra_payloads = present_payloads - allowed_payloads
        if extra_payloads:
            extra_list = ", ".join(sorted(extra_payloads))
            raise ValueError(
                f"Condition node `{self.kind}` must not declare payload field(s): {extra_list}."
            )

        missing_payloads = self._missing_required_payloads()
        if missing_payloads:
            missing_list = ", ".join(sorted(missing_payloads))
            raise ValueError(
                f"Condition node `{self.kind}` requires payload field(s): {missing_list}."
            )
        return self


class DynamicCondition(ConditionNode):
    pass


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
    when: ConditionNode
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


class WorldState(BaseModel):
    current_time: int = 8 * 60
    agent: AgentState
    areas: dict[str, Area] = Field(default_factory=dict)
    locations: dict[str, Location]
    objects: dict[str, WorldObject] = Field(default_factory=dict)
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


WorldEventRule.model_rebuild()
ConditionNode.model_rebuild()
DynamicCondition.model_rebuild()
