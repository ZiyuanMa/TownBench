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

这种模型足够支持“镇上几个地点”的场景，但不擅长表达：

- 一栋建筑内有多个房间
- 建筑内部移动应比跨建筑移动更自然
- 观测中需要“当前建筑/区域”的语义

本提案的目标是：

- 为 benchmark 提供“建筑/区域”这一层语义结构
- 保持 runtime 核心规则简单、可解释
- 为后续更复杂的室内任务流预留扩展点

## 核心设计

### 1. `Location` 仍是唯一导航目标

`move_to` 继续只接受 `location_id`。

原因：

- 当前 runtime、对象可达性、事件传送都以 `location_id` 为核心键
- `Location` 是“可站立、可交互、可放对象”的最小单元
- 如果改成 `move_to(area_id)`，会引入“进入区域后落在哪个房间”的歧义

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

1. 若目标 `location_id` 不存在，失败
2. 若当前 `Location.area_id` 与目标 `Location.area_id` 相同，且不为 `None`，则允许移动
3. 否则，仍要求目标 `location_id` 出现在当前 `Location.links` 中
4. 否则判定为不可达

等价语义：

- 同一建筑/区域内的房间默认互通
- 跨区域移动仍然需要显式出口/入口点

这可以显著简化“建筑内部房间切换”的 authoring 成本。

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
    location_ids: list[str] = Field(default_factory=list)
```

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

其中 `Area.location_ids` 为 loader 派生字段，不接受 authored YAML 直接填写。

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
- 派生 `Area.location_ids`
- 将 `areas` 写入最终 `WorldState`

建议保留的边界：

- `Location.object_ids` 仍由 loader 组装
- `Area.location_ids` 也由 loader 组装
- authored YAML 不直接声明这两个派生字段

建议新增的校验规则：

- area id 唯一
- location 引用的 `area_id` 必须存在
- 旧场景允许没有 `areas`

## Runtime 行为影响

### `move_to`

只改可达性判断，不改入参形式，不改动作名称。

建议实现逻辑：

```python
current_location = state.locations[state.agent.location_id]
target_location = state.locations.get(action.target_id)

if target_location is None:
    ...
if (
    current_location.area_id is not None
    and current_location.area_id == target_location.area_id
):
    reachable = True
else:
    reachable = action.target_id in current_location.links
```

### 对象可达性

不改。

对象仍必须满足：

- `world_object.location_id == agent.location_id`

不要放宽为“同 `Area` 即可访问”，否则会削弱房间边界，并增加解释复杂度。

### 事件与对象动作传送

暂不改语义：

- `move_to_location_id` 继续只接受 `location_id`
- 事件规则与对象效果不引入 `area_id`

## Observation 设计

v1 中建议让 agent 看到有限但有用的 `Area` 信息。

新增建议字段：

```python
class AreaObservation(BaseModel):
    area_id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
```

扩展 `Observation`：

```python
class Observation(BaseModel):
    ...
    current_area: AreaObservation | None = None
    same_area_locations: list[str] = Field(default_factory=list)
    linked_area_locations: list[str] = Field(default_factory=list)
```

语义：

- `current_area`：当前地点所属区域
- `same_area_locations`：当前区域内其他可直接到达的地点
- `linked_area_locations`：当前地点通过显式 `links` 可跨区域到达的地点

这样可以帮助 agent：

- 理解自己位于哪个建筑/区域
- 理解该区域内还有哪些房间
- 理解从当前出口可前往哪些外部地点

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

1. 在 runtime 中新增 `Area`、`Location.area_id`、`WorldState.areas`
2. 在 scenario schema 与 loader 中支持 `areas`
3. 在 loader 中实现 `Area.location_ids` 派生与 area 校验
4. 修改 `move_to` 的可达性规则为“同 area 默认互通，否则看 links”
5. 扩展 observation，暴露当前 area 与同 area 地点信息
6. 补充 loader / transition / observation 回归测试
7. 新增 `library_operations` 场景及其集成测试
8. 更新 `docs/architecture.md`

## 验收标准

- 新场景可表达“一个建筑内多个房间”
- 同一 `Area` 内无需 authored `links` 也能正常移动
- 跨 `Area` 移动仍需显式连接点
- 对象仍只在当前 `Location` 内可访问
- 不带 `Area` 的旧场景行为完全不变
- 新增 observation 能明确展示当前 `Area`

## 暂不纳入本次工作的内容

以下内容不应并入 v1：

- 多层 area
- area 级链接 authored schema
- area 级移动动作
- area 级对象访问
- area 级事件规则
- 自动推导 area 邻接图并用于真实移动

这些能力都可能有价值，但会显著放大当前改动范围，不适合和 v1 一起落地。
