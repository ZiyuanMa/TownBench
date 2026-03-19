# 重构提案：消除 scenario/schema.py 与 engine/state.py 的模型重复

## 问题描述

当前 `scenario/schema.py` 为 engine 中几乎每个数据模型都创建了一个镜像
`Scenario*Source` 类（共 9 个），字段与 engine 模型几乎完全一致，再通过
`to_xxx()` 方法逐字段拷贝到 engine 模型。

### 重复对照表

| Scenario Schema 类 | Engine State 类 | 差异 |
|---------------------|-----------------|------|
| `ScenarioAgentStateSource` | `AgentState` | **无** |
| `ScenarioActionCostSource` | `ActionCost` | **无** |
| `ScenarioTerminationConfigSource` | `TerminationConfig` | **无** |
| `ScenarioEventRuleSource` | `WorldEventRule` | **无** |
| `ScenarioObjectActionEffectSource` | `ObjectActionEffect` | **无** |
| `ScenarioLocationSource` | `Location` | 少 `object_ids`（运行时派生） |
| `ScenarioObjectSource` | `WorldObject` | 多 `resource_file`（仅加载时需要） |
| `ScenarioInitialWorldState` | — | 仅容器，可提升为顶层字段 |
| `ScenarioSkillSource` | `Skill` | 不同结构（`file` vs `content`） |

> 其中 5 个类的字段完全一致，单纯手工复制了 engine 模型。

### 影响

- 每次给 engine 模型加字段，必须同步修改 schema 和 `to_xxx()` 方法。
- 大量视觉相似但语义相同的代码增加了认知负担（schema.py 共 231 行）。
- `to_xxx()` 方法中的逐字段拷贝容易遗漏新增字段。

---

## 推荐方案：engine 模型直接作为 schema

### 核心思路

1. 给 engine 模型加 `model_config = ConfigDict(extra="forbid")`，使其兼具输入校验能力。
2. `ScenarioConfig` 直接引用 engine 模型，消除中间的 `Scenario*Source` 类。
3. 对于真正存在差异的模型，使用**继承**而非重写。

### 变更明细

#### 1) 完全消除（5 个零差异类）

直接删除以下类及其 `to_xxx()` 方法，`ScenarioConfig` 改为引用 engine 类型：

```python
# scenario/schema.py — 删除
ScenarioAgentStateSource       # → 直接用 AgentState
ScenarioActionCostSource       # → 直接用 ActionCost
ScenarioTerminationConfigSource # → 直接用 TerminationConfig
ScenarioEventRuleSource        # → 直接用 WorldEventRule
ScenarioObjectActionEffectSource # → 直接用 ObjectActionEffect
```

对 engine 端这些模型添加：

```python
class ActionCost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # ... 字段不变
```

#### 2) 继承处理（2 个有差异类）

**Location**（scenario 不允许 `object_ids`，它是运行时派生的）：

```python
# scenario/schema.py
class ScenarioLocationSource(Location):
    model_config = ConfigDict(extra="forbid")
    object_ids: ClassVar[None] = None  # 禁止此字段出现

    @model_validator(mode="before")
    @classmethod
    def reject_object_ids(cls, data):
        if isinstance(data, dict) and "object_ids" in data:
            raise ValueError("...")
        return data
```

**WorldObject**（scenario 多一个 `resource_file` 字段）：

```python
# scenario/schema.py
class ScenarioObjectSource(WorldObject):
    model_config = ConfigDict(extra="forbid")
    resource_file: Optional[str] = None

    @model_validator(mode="after")
    def validate_resource_source(self):
        if self.resource_content and self.resource_file:
            raise ValueError("...")
        return self
```

#### 3) 提升 `ScenarioInitialWorldState`

将其两个字段直接放到 `ScenarioConfig` 顶层：

```python
class ScenarioConfig(BaseModel):
    current_time: str = "Day 1, 08:00"
    world_flags: dict[str, bool] = Field(default_factory=dict)
    # ... 其余字段
```

对应的 YAML 格式也做扁平化调整（向后兼容方案：保留嵌套格式，用
`model_validator` 展开）。

#### 4) `ScenarioSkillSource` 保留

`ScenarioSkillSource` 只有 `skill_id` + `file`，与 `Skill`（有 `content`）
结构不同，加载时需要读取文件内容。此类保持现状，但无需 `to_xxx()` 方法，
在 loader 中直接构造 `Skill`。

### loader.py 简化

```diff
-def _build_locations(config: ScenarioConfig) -> dict[str, Location]:
-    return {item.location_id: item.to_location() for item in config.locations}
+def _build_locations(config: ScenarioConfig) -> dict[str, Location]:
+    return {item.location_id: Location(**item.model_dump(exclude={"resource_file"}))
+            for item in config.locations}
```

> 对于零差异类，连 `model_dump()` 转换都不需要——直接使用即可。

---

## 预期效果

- 删除约 **150 行** `scenario/schema.py` 中的重复代码。
- 消除 5 个 `to_xxx()` 方法，新增字段只需改一处。
- `schema.py` 从 231 行缩减至约 80 行。

## 风险

- 需要给 engine 模型加 `extra="forbid"`，检查是否有运行时代码依赖动态属性。
- YAML 反序列化直接到 engine 模型，需确保 Pydantic v2 的 `model_validate`
  行为与当前一致。
- `ScenarioInitialWorldState` 的扁平化需要同步更新所有 scenario.yaml 文件
  或提供兼容 validator。

## 建议验证步骤

1. 先对 5 个零差异类做消除，运行全部测试确认绿灯。
2. 再处理 `ScenarioLocationSource` 和 `ScenarioObjectSource` 的继承改造。
3. 最后考虑 `ScenarioInitialWorldState` 的扁平化（可选，属于锦上添花）。
