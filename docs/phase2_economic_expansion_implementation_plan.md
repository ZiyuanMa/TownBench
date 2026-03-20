# Phase 2 Economic Expansion Implementation Plan

## 目标

本文档将 [phase2_economic_expansion_plan.md](./phase2_economic_expansion_plan.md) 中的环境设计目标，转换为可执行的代码修改计划。

本阶段的实现目标不是引入一个更通用的大型模拟器，而是在保持 TownBench 当前“作者驱动、可解释、确定性较强”风格的前提下，补足少量通用机制，让环境能够稳定承载小型经营闭环。

## 实现原则

- 优先复用现有 TownBench 架构，不新增脚本解释器或通用规则语言。
- Phase 2 的核心新增能力应尽量少而通用，避免为单一场景写硬编码。
- 优先实现“可重复运行的小经营循环”，再补齐扩容、恢复、维护等压力。
- 不在本阶段实现深仓储、复杂 NPC、随机价格或多日债务系统。
- Scoring 继续以 `final_money` 为主，不引入 loop-specific 正式指标。

## 总体结论

当前引擎已经支持以下能力：

- 多地点移动
- 可读资源与技能
- 基于 `inventory`、`money`、`world_flags` 的对象动作前置条件
- 基于 `inventory`、`money`、`energy`、`visible_state`、`world_flags` 的对象动作副作用
- 事件规则和终止规则

Phase 2 真正缺失的能力主要有两项：

1. 轻量库存容量约束
2. 可由场景动作修改和校验的 agent 数值状态

其余多数 Phase 2 内容都可以继续用已有的“对象动作 + 物品消耗 + 文档提示 + 可见状态”模型实现。

## 推荐实现范围

### 本阶段必须实现

- `carry_limit` 或 `inventory_capacity` 形式的背包容量限制
- 对 agent 数值状态的读取、校验、变更支持
- 一个新的 `phase2_town` 场景
- 至少 3 条可重复经营循环
- 至少 1 条容量扩张决策
- 至少 1 条坏库存恢复路径
- 完整测试覆盖

### 本阶段明确不做

- 对象级库存容器
- 通用表达式求值
- 基于时间窗口的动态价格
- 随机事件
- 深度维修耐久树
- 多代理或 NPC 经济行为

## 数据模型与引擎改动

### 1. 扩展对象动作效果

当前 `ObjectActionEffect` 只支持：

- `required_world_flags`
- `required_inventory`
- `required_money`
- `money_delta`
- `energy_delta`
- `inventory_delta`
- `set_visible_state`
- `set_world_flags`
- `move_to_location_id`

建议新增两个字段：

- `required_agent_stats: dict[str, int]`
- `agent_stat_deltas: dict[str, int]`

语义建议如下：

- `required_agent_stats`
  - 表示动作执行前，agent 的对应数值状态至少需要达到给定值
  - 示例：`carry_limit >= 5`、`cart_rental_active >= 1`
- `agent_stat_deltas`
  - 表示动作执行后，对 agent 数值状态施加增减
  - 示例：租用扩容后 `carry_limit +3`

不建议本阶段引入 `set_agent_stats`。如果动作语义需要“恢复到某个固定值”，优先通过有界增量或场景约束表达；否则容易过早进入更复杂的状态 DSL 设计。

### 2. 正式启用 `AgentState.stats`

`AgentState.stats` 已经存在，但当前未参与动作判定，也未投影到 observation 中。

Phase 2 里建议将其正式用于以下用途：

- `carry_limit`
- 可选：`base_carry_limit`
- 可选：`cart_capacity_bonus`

建议约定：

- 容量判定只依赖一个最终字段，例如 `carry_limit`
- 不在本阶段实现“按时间失效”的 buff
- 扩容可以设计为本局持续，降低引擎复杂度

### 3. 引入轻量库存容量校验

建议新增一个统一的库存占用计算规则：

- 默认占用按物品数量总和计算
- Phase 2 暂不引入重量系统
- 可将少数“大件物品”直接定义为数量为 1 但利润更高，先不做权重

建议新增辅助逻辑：

- 计算当前 inventory 总占用
- 从 `agent.stats["carry_limit"]` 读取容量上限
- 在统一的 inventory delta 应用路径上做容量预校验，而不是只在对象动作 handler 中单独判断
- 该校验应同时覆盖 `ObjectActionEffect.inventory_delta`、`ActionCost.inventory_delta` 以及二者在同一步中的合并结果

建议行为：

- 若 `carry_limit` 未设置，则视为无限容量，保持旧场景兼容
- 若对象动作本身或动作成本会使库存超上限，则整步失败，并返回结构化失败，例如 `inventory_capacity_exceeded`
- 不允许出现“对象动作已生效，但随后因 action cost 超容量而进入部分提交状态”

### 4. Observation 与 status 暴露

Phase 2 若引入容量，agent 必须能看到自己的容量状态。

建议修改：

- `Observation.agent` 增加 `stats`
- `check_status` payload 增加 `stats`

不建议把所有内部统计都隐藏起来再要求 agent 自己推断，这会让 benchmark 更像“信息缺失题”，而不是经营管理题。

### 5. 事件规则保持简单

本阶段不建议修改 `event_rules` 的结构。

原因：

- Phase 2 主要压力来自经营闭环，而不是复杂自动事件
- 容量、维护、恢复都可以通过对象动作和已有 `world_flags` 实现
- 若未来确实需要基于 stats 的自动事件，再单独扩展

## 场景实现方案

### 新场景

新增目录：

- `scenarios/phase2_town/scenario.yaml`
- `scenarios/phase2_town/resources/`
- `scenarios/phase2_town/skills/`

建议复用 `phase1_town` 的整体地理风格，但让经济关系更闭合。

### 推荐地点

- `plaza`
- `market`
- `workshop`
- `canteen`
- `supply_shop`
- `storage_room`
- `service_depot`
- `fuel_counter`

可选：

- `library`
- `station`

### 推荐经营循环

#### Loop A: Tea Production Loop

目标：把 Phase 1 的茶流程改造成可持续经营流程。

核心物品：

- `tea_bundle`
- `fuel_canister`
- `brewed_tea`
- `packaging_sleeve`
- `packed_tea`

推荐动作链：

1. 在 `market` 购买 `tea_bundle`
2. 在 `fuel_counter` 或 `supply_shop` 购买 `fuel_canister`
3. 在 `workshop/tea_station` 把 `tea_bundle` 转成 `brewed_tea`
4. 在 `workshop/packaging_table` 消耗 `packaging_sleeve` 包装为 `packed_tea`
5. 在 `market/goods_buyer` 出售 `packed_tea`

关键经营压力：

- 必须持续补 fuel
- 必须持续补 packaging
- 收益发生在多步之后

#### Loop B: Prepared Meal Loop

目标：提供低资本、较稳定的 fallback loop。

核心物品：

- `meal_ingredients`
- `meal_box`

推荐动作链：

1. 在 `market/ingredient_seller` 买 `meal_ingredients`
2. 在 `workshop/meal_prep_table` 制作 `meal_box`
3. 在 `canteen/kitchen_contract_board` 或 `meal_counter` 交付

关键经营压力：

- 单次利润不高
- 但启动资金低，适合作为现金不足时的恢复路径

#### Loop C: Repair Service Loop

目标：提供更高利润但更依赖工作资本的服务循环。

核心物品：

- `repair_part`
- `serviced_device_ticket` 或直接 payout

推荐动作链：

1. 在 `supply_shop/parts_bin` 购买 `repair_part`
2. 在 `workshop/repair_bench` 执行维修
3. 在 `service_depot/pickup_clerk` 领取报酬

关键经营压力：

- 启动成本高于 meal loop
- 若中途现金断裂，agent 更容易卡住

#### Loop D: Capacity Expansion Loop

目标：让扩容成为经济决策，而不是纯背景设定。

建议实现方式：

- 不做真实仓库存取
- 直接用 `locker_desk` 或 `cart_rental` 提供 `carry_limit +N`
- 扩容动作必须配套一次性 gating
- 推荐做法：用 `required_world_flags` + `set_world_flags` 保证单个扩容档位只能购买一次
- 本阶段不支持无上限叠加购买

推荐动作链：

1. 支付扩容费用
2. 背包上限提升
3. 批量购买低单价原料
4. 连续加工或批量出售

关键经营压力：

- 先付成本，后吃吞吐收益
- 若升级过早，可能造成现金压力

## 坏状态与恢复路径

### 1. 零现金陷阱

设计方式：

- 茶循环需要多个输入才能最终变现
- 若 agent 过早买入错误物料，可能无法完成最后一步

恢复方式：

- 提供低利润 meal loop
- 或允许以折价卖出部分中间品/原料

### 2. 坏库存占满容量

设计方式：

- 让部分低价值商品也可购买
- 容量变成真实约束

恢复方式：

- `goods_buyer` 低价回收部分货物
- 或 `discard_bin` 无收益清库存

### 3. 维护忽略

设计方式：

- 茶循环需要 fuel
- 包装需要 sleeves
- repair loop 需要 parts

恢复方式：

- supply network 随时可补货
- 但多走一步、多付一笔钱，收益变差

## 测试计划

### 1. 引擎级测试

新增或修改测试覆盖以下行为：

- `required_agent_stats` 能正确阻止动作执行
- `agent_stat_deltas` 能正确更新状态
- `carry_limit` 未设置时保持旧行为
- `carry_limit` 设置后，`ObjectActionEffect.inventory_delta` 超容量会失败
- `carry_limit` 设置后，`ActionCost.inventory_delta` 超容量也会失败
- `carry_limit` 设置后，对象动作 effect 与 action cost 合并后超容量时整步失败，且不会留下部分状态变更
- `Observation.agent.stats` 与 `check_status` 能反映最新状态

### 2. Schema / Loader 测试

新增或修改 `tests/test_scenario_loader.py`，至少覆盖：

- 新增字段 `required_agent_stats` / `agent_stat_deltas` 能被正确解析
- 旧场景在不声明这些字段时仍可正常加载
- `phase2_town` 中扩容动作的 authoring 明确采用一次性 gating，不允许无限叠加购买

### 3. 场景级测试

新增 `tests/test_phase2_scenario.py`，至少覆盖：

- 场景成功加载
- tea loop 可重复盈利
- meal loop 可作为低资本 fallback
- repair loop 利润高但需要更高启动成本
- 扩容前无法完成某个批量动作，扩容后可以
- 错误购买导致库存压力，但仍有恢复路径

### 4. 回归测试

必须确认以下内容不被破坏：

- `phase1_town` 仍能加载并通过原测试
- 旧场景在没有 `carry_limit` 时不受影响
- OpenAI baseline 工具定义不需要改动动作接口

## 文件修改清单

### 引擎与 schema

- `engine/state.py`
  - 扩展 `ObjectActionEffect`
- `scenario/schema.py`
  - 扩展 `ScenarioObjectActionEffectSource`
- `engine/action_handlers.py`
  - 增加 agent stats 判定与变更
- `engine/transition.py`
  - 在整步效果提交前统一处理 capacity 预校验，避免 object effect / action cost 语义分裂
- `engine/rules.py`
  - 提供 inventory 占用计算与 capacity 校验辅助逻辑
- `engine/observation.py`
  - 暴露 `agent.stats`
- `tests/test_transition.py`
  - 增加 stats/capacity 相关测试
- `tests/test_observation.py`
  - 更新 observation 断言
- `tests/test_scenario_loader.py`
  - 增加新增字段和兼容性测试

### 场景内容

- `scenarios/phase2_town/scenario.yaml`
- `scenarios/phase2_town/resources/*`
- `scenarios/phase2_town/skills/*`
- `tests/test_phase2_scenario.py`

### 文档

- `docs/architecture.md`
  - 在引擎能力和场景 schema 部分补充 agent stats / capacity 机制
- 本文档

## 分阶段实施顺序

### 阶段 1: 引擎最小增强

目标：

- stats 可参与动作执行
- 容量限制可生效
- observation 可见 stats

完成标准：

- 单元测试通过
- 旧场景不回归

### 阶段 2: 落地基础 Phase 2 场景

目标：

- 建立 tea loop
- 建立 meal loop
- 提供必要资源文档与技能提示

完成标准：

- 低复杂度循环已闭环
- agent 可以在不同现金状态下切换循环

### 阶段 3: 引入高利润维修循环

目标：

- 加入 repair loop
- 拉开不同 loop 的资本门槛

完成标准：

- repair loop 能稳定跑通并形成高于 fallback loop 的单轮收益
- repair loop 的启动成本高于 meal loop，且在低现金初始状态下不可直接进入
- 场景测试能验证 agent 需要先通过低资本 loop 积累工作资本，才能进入更高利润 loop

### 阶段 4: 引入容量扩张与恢复路径

目标：

- 扩容成为真实经济决策
- 坏库存和恢复路径可见

完成标准：

- 扩容有时正确，有时过早
- trace 中能观察到吞吐决策和恢复决策

## 验收标准

Phase 2 完成后，应满足以下条件：

- 环境中至少存在 3 条可重复经营循环
- 至少有 1 条循环依赖持续补货或维护消耗
- 至少有 1 条循环在低现金状态下仍可作为 fallback
- 至少有 1 个扩容决策会影响最优策略
- 错误采购或过早升级会造成可恢复但有代价的坏状态
- trace 中可以清楚看到“经营循环”而不是单次离散收益动作

## 推荐下一步

按本文档执行时，建议先做“阶段 1: 引擎最小增强”。

原因：

- 这是后续场景内容能否表达容量和扩容决策的基础
- 改动范围集中，测试边界清晰
- 做完后再写 `phase2_town`，返工最少
