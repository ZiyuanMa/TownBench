# 设计提案：为 TownBench 引入单层 `Area` 与多房间 `Location`

## 结论

这项改动值得做，但应收敛为一次**中小规模的建模增强**，而不是地图系统重写。

建议的 v1 范围是：

- 新增单层 `Area`，用于表达建筑/区域分组
- `Location` 继续作为 agent 实际站立、移动和交互的最小节点
- `move_to` 继续以 `location_id` 为目标
- 同一 `Area` 内的 `Location` 默认互通
- 跨 `Area` 移动仍通过显式 `location.links` 表达
- 保持旧场景完全兼容

不建议在 v1 同时引入：

- 多层 `Area`
- `move_to(area_id)`
- `Area.links`
- 区域级对象可达性
- 区域级事件传送

## 背景与目标

当前 TownBench 的地点系统是单层扁平图：

- `AgentState` 只持有一个 `location_id`
- `Location.links` 决定所有移动关系
- 对象仅通过 `object.location_id == agent.location_id` 判断可达
- 观测中只暴露当前 `Location`

这种模型足够支持"镇上几个地点"的场景，但不擅长表达：

- 一栋建筑内有多个房间
- 建筑内部移动应比跨建筑移动更自然
- 观测中需要"当前建筑/区域"的语义

本提案的目标是：

- 为 benchmark 提供"建筑/区域"这一层语义结构
- 保持 runtime 核心规则简单、可解释
- 为后续更复杂的室内任务流预留扩展点

## 核心设计

### 1. `Location` 仍是唯一导航目标

`move_to` 继续只接受 `location_id`。

原因：

- 当前 runtime、对象可达性、事件传送都以 `location_id` 为核心键
- `Location` 是"可站立、可交互、可放对象"的最小单元
- 如果改成 `move_to(area_id)`，会引入"进入区域后落在哪个房间"的歧义

因此：

- `Area` 是语义分组
- `Location` 是实际导航节点

### 2. `Area` 仅有一层

v1 中，`Area` 不支持 `parent_area_id`。

一个 `Location` 可以：

- 属于某个 `Area`
- 或不属于任何 `Area`，保持 `area_id = null`

这样可以保证：

- 新设计足够简单
- 旧场景不需要立即迁移

### 3. 同 `Area` 默认互通

移动规则调整为：

1. 若目标 `location_id` 与当前 `location_id` 相同，直接成功（自移动短路）
2. 若目标 `location_id` 不存在，失败
3. 若当前 `Location.area_id` 与目标 `Location.area_id` 相同，且不为 `None`，则允许移动
4. 否则，仍要求目标 `location_id` 出现在当前 `Location.links` 中
5. 否则判定为不可达

等价语义：

- 自移动（move_to 当前位置）直接返回成功，仍消耗 action cost
- 同一建筑/区域内的房间默认互通
- 跨区域移动仍然需要显式出口/入口点

这可以显著简化"建筑内部房间切换"的 authoring 成本。

### 4. `location.links` 在 v1 中主要承担跨 `Area` 连接

在引入 `Area` 后，`links` 的主要作用变为：

- 表达跨 `Area` 的连接点
- 表达不属于任何 `Area` 的扁平地点连接

同一 `Area` 内通常不需要再手写 `links`。

例如：

- `library_lobby.area_id = library`
- `reading_room.area_id = library`
- `archive_room.area_id = library`

则：

- `library_lobby -> archive_room` 无需显式 `links`
- `reading_room -> library_lobby` 无需显式 `links`
- 但 `library_lobby -> plaza` 需要显式 `links`

## 数据模型建议

### Runtime model

在 `engine/state.py` 中新增：

```python
class Area(BaseModel):
    area_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
```

`Area` 不存储 `location_ids`。需要时通过遍历 `WorldState.locations` 中
`area_id` 匹配的 `Location` 动态计算，避免 state 中出现冗余派生数据。

扩展 `Location`：

```python
class Location(BaseModel):
    ...
    area_id: str | None = None
```

扩展 `WorldState`：

```python
class WorldState(BaseModel):
    ...
    areas: dict[str, Area] = Field(default_factory=dict)
```

### Scenario schema

在 `scenario/schema.py` 中新增：

```python
class ScenarioAreaSource(BaseModel):
    area_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
```

扩展 `ScenarioLocationSource`：

```python
area_id: str | None = None
```

扩展 `ScenarioConfig`：

```python
areas: list[ScenarioAreaSource] = Field(default_factory=list)
```

## Loader 责任与校验

`scenario/loader.py` 应新增以下职责：

- 校验 `area_id` 唯一
- 校验 `Location.area_id` 若存在，必须引用已知 `Area`
- 将 `areas` 写入最终 `WorldState`

建议保留的边界：

- `Location.object_ids` 仍由 loader 组装
- authored YAML 不直接声明 `object_ids` 派生字段

建议新增的校验规则：

- area id 唯一
- location 引用的 `area_id` 必须存在
- 旧场景允许没有 `areas`

## Runtime 行为影响

### `move_to`

只改可达性判断，不改入参形式，不改动作名称。

建议实现逻辑：

```python
# 自移动短路
if action.target_id == state.agent.location_id:
    return _success("You are already here.")

current_location = state.locations[state.agent.location_id]
target_location = state.locations.get(action.target_id)

if target_location is None:
    ...

# 同 Area 内部互通
if (
    current_location.area_id is not None
    and current_location.area_id == target_location.area_id
):
    reachable = True
else:
    reachable = action.target_id in current_location.links
```

自移动返回 `_success`，transition engine 仍会正常扣除 action cost。
这样 agent 会学到"不要原地踏步"。

### 对象可达性

不改。

对象仍必须满足：

- `world_object.location_id == agent.location_id`

不要放宽为"同 `Area` 即可访问"，否则会削弱房间边界，并增加解释复杂度。

### 事件与对象动作传送（`move_to_location_id`）

`ObjectActionEffect.move_to_location_id` 为效果传送语义，**不受 Area/links
可达性约束**。场景作者通过声明 `move_to_location_id` 来表达"此动作可将
agent 传送到指定地点"。这与 `move_to` 的导航语义不同。

具体规则：

- `move_to_location_id` 继续只接受 `location_id`
- 只校验目标 `location_id` 是否存在，不检查 links 或 Area 可达
- 事件规则不引入 `area_id`

## Observation 设计

v1 中建议让 agent 看到有限但有用的 `Area` 信息。

新增建议字段：

```python
class AreaObservation(BaseModel):
    area_id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
```

`AreaObservation` 不包含 `location_ids`，保持与 `Area` 模型一致。
同 Area 内的可达地点通过 `Observation.nearby_locations` 表达。

扩展 `Observation`：

```python
class Observation(BaseModel):
    ...
    current_area: AreaObservation | None = None
    nearby_locations: list[str] = Field(default_factory=list)
```

字段语义：

- `current_location.links`：保持不变，仅包含 authored links（YAML 中显式声明的连接）
- `current_area`：当前地点所属区域的语义信息（名称、描述、tags）
- `nearby_locations`：从当前位置可以 `move_to` 到达的**所有地点**（同 Area 隐式可达 + authored links 的并集，去重排序）

投影逻辑：

```python
def _build_nearby_locations(state: WorldState, current_location: Location) -> list[str]:
    nearby: set[str] = set(current_location.links)
    if current_location.area_id is not None:
        for loc in state.locations.values():
            if (
                loc.area_id == current_location.area_id
                and loc.location_id != current_location.location_id
            ):
                nearby.add(loc.location_id)
    return sorted(nearby)
```

设计理由：

- agent 最终关心的是"我能去哪"，一个 `nearby_locations` 足以表达
- Area 归属信息已通过 `current_area` 传达，无需在可达列表中再做分类
- 减少 agent 需要理解的字段数量，降低 prompt 解释成本

这样可以帮助 agent：

- 通过 `current_area` 理解自己位于哪个建筑/区域
- 通过 `nearby_locations` 一次性看到所有可移动目标
- 不需要自己做集合运算来判断可达性

## YAML authoring 草案

```yaml
scenario_id: library_operations

areas:
  - area_id: library
    name: Library
    description: Main public library building.

  - area_id: market_block
    name: Market Block
    description: Outdoor plaza and supply services.

locations:
  - location_id: plaza
    area_id: market_block
    name: Plaza
    description: A central outdoor square.
    links: [library_lobby]

  - location_id: library_lobby
    area_id: library
    name: Library Lobby
    description: Entry hall with the front desk.
    links: [plaza]

  - location_id: reading_room
    area_id: library
    name: Reading Room
    description: Quiet tables for review work.

  - location_id: archive_room
    area_id: library
    name: Archive Room
    description: Shelves of archived documents.
```

在这个例子中：

- `library_lobby`、`reading_room`、`archive_room` 同属 `library`
- 三者之间默认互通
- 但离开 `library` 去 `plaza`，仍要通过显式连接点 `library_lobby`

## 推荐场景：`library_operations`

为了让 `Area` 不是纯标签，建议增加一个专门使用该设计的新场景。

### Area 划分

建议 3 个 `Area`：

- `library`
- `market_block`
- `service_hub`

### Location 分布

`library`：

- `library_lobby`
- `reading_room`
- `archive_room`
- `staff_office`
- `sorting_room`

`market_block`：

- `plaza`
- `supply_shop`
- `courier_stop`

`service_hub`：

- `maintenance_desk`
- `break_room`
- `storage_room`

### 任务循环

主循环建议为：

1. 在 `library_lobby` 接单
2. 在 `staff_office` 领取权限或登记任务
3. 在 `archive_room` 取资料
4. 在 `reading_room` 核对内容
5. 在 `sorting_room` 打包
6. 在 `courier_stop` 交付并领取报酬
7. 返回 `library_lobby` 接下一单

这样可以直接验证：

- 同 `Area` 默认互通是否降低了无意义导航成本
- agent 是否能利用 `Area` 信息进行分区规划
- 跨 `Area` 出入口是否足够清晰

## 向后兼容策略

必须保证现有场景零修改可继续运行。

具体策略：

- `areas` 默认为空
- `Location.area_id` 默认为 `None`
- 若当前或目标 `Location` 没有 `area_id`，则仍完全依赖 `links`

因此旧场景的行为应保持不变。

## 实施顺序

每步完成后立即编写对应测试，避免最后统一补测时发现前面的实现问题。

1. `engine/state.py`：新增 `Area`、`Location.area_id`、`WorldState.areas`
   - 测试：模型序列化/反序列化、`area_id` 默认 `None`、`areas` 默认空

2. `scenario/schema.py`：新增 `ScenarioAreaSource`、`ScenarioLocationSource.area_id`、
   `ScenarioConfig.areas`
   - 测试：YAML 级别的 parse 和 `extra=forbid` 校验

3. `scenario/loader.py`：area 唯一性校验、`area_id` 引用校验、`_build_world_state` 写入 areas
   - 测试：area_id 引用不存在 area 报错、重复 area_id 报错、无 areas 的旧场景正常通过

4. `engine/action_handlers.py`：`_handle_move_to` 加自移动短路 + Area 内互通判断
   - 测试：自移动返回成功、同 Area 无 link 可达、跨 Area 有 link 可达、跨 Area 无 link 不可达、无 Area 的旧行为不变

5. `engine/observation.py`：新增 `AreaObservation`、`nearby_locations`、扩展 `project_observation`
   - 测试：`current_area` 正确投影、`nearby_locations` 包含同 Area + links 的并集、无 Area 时 `current_area` 为 `None`

6. Baseline 适配：更新 `move_to` tool description、在场景 `public_rules` 中增加 Area 说明

7. 新增 `library_operations` 场景及其集成测试

8. 更新 `docs/architecture.md`

## 验收标准

- 新场景可表达"一个建筑内多个房间"
- 同一 `Area` 内无需 authored `links` 也能正常移动
- 跨 `Area` 移动仍需显式连接点
- 对象仍只在当前 `Location` 内可访问
- 不带 `Area` 的旧场景行为完全不变
- 新增 observation 能明确展示当前 `Area`
- 自移动（move_to 当前位置）返回成功且不影响状态

## Baseline Agent 适配

引入 Area 后，Observation 的 JSON 结构会自动包含 `current_area` 和
`nearby_locations`，但需要通过以下方式帮助 agent 理解新字段：

1. 在场景 `public_rules` 中增加说明：

```yaml
public_rules:
  - >-
    Locations may belong to an Area (a building or district).
    You can move freely between locations in the same Area
    without needing explicit connections. Use `nearby_locations`
    in your observation to see all reachable locations.
```

2. 更新 `move_to` 的 tool description：

```
Move to a connected location. Locations in the same area are always
reachable. Cross-area movement requires an explicit connection.
```

3. 确认 `baselines/openai_agents/tools.py` 动态生成的工具签名中，
   description 能正确反映新的可达规则。

## 可达性边界 Case 参考

| Case | 当前 area_id | 目标 area_id | links 中有目标？ | 结果 |
|------|-------------|-------------|-----------------|------|
| 自移动 | 任意 | 同 location | N/A | 成功（no-op） |
| 同 Area | `library` | `library` | 否 | 可达 |
| 跨 Area 有 link | `library` | `market` | 是 | 可达 |
| 跨 Area 无 link | `library` | `market` | 否 | 不可达 |
| 当前无 Area | `None` | `library` | 是 | 可达 |
| 当前无 Area | `None` | `library` | 否 | 不可达 |
| 目标无 Area | `library` | `None` | 否 | 不可达 |
| 双方无 Area | `None` | `None` | 否 | 不可达 |

## 暂不纳入本次工作的内容

以下内容不应并入 v1：

- 多层 area
- area 级链接 authored schema
- area 级移动动作
- area 级对象访问
- area 级事件规则
- 自动推导 area 邻接图并用于真实移动
- 统一 scenario schema 与 engine state 的叶子模型（Area / Location 等的 schema 镜像问题应在单独的重构提案中解决）

这些能力都可能有价值，但会显著放大当前改动范围，不适合和 v1 一起落地。
