# 重构提案：收缩 `scenario/schema.py` 中的低价值重复

## 结论

这个重构仍然有必要，但应该被视为一个**小范围维护性清理**，而不是架构级改造。

建议把目标收敛为：

- 删除几类明显的镜像 leaf model
- 减少低价值 `to_xxx()` 样板
- 保留 authoring schema 和 runtime model 的分层边界
- 不修改 scenario YAML 结构
- 不改变 loader 的职责分工

不建议继续追求“让 `engine.state` 直接充当 scenario schema”。

## 这件事为什么还值得做

当前 `scenario/schema.py` 里，确实有一部分模型只是对 `engine/state.py` 中叶子模型的重复包装：

- `ScenarioAgentStateSource`
- `ScenarioActionCostSource`
- `ScenarioObjectActionEffectSource`
- `ScenarioEventRuleSource`
- `ScenarioTerminationConfigSource`

这些类的问题是：

- 字段基本重复
- `to_xxx()` 主要是在做机械拷贝
- runtime model 增字段时，schema 侧容易漏改

这类重复不会立刻造成行为 bug，但会持续提高维护成本。

## 为什么不值得大做

当前 loader 仍然承担明确且必要的装配职责：

- 校验 authored id 唯一性
- 校验 location / object / event 引用
- 解析 `resource_file`
- 解析 skill frontmatter
- 组装 `location.object_ids`
- 派生 `WorldObject.actionable`

这些行为在 [`scenario/loader.py`](/Users/ziyuanma/Desktop/TownBench/scenario/loader.py) 中都是真正的加载逻辑，不是可以顺手“去重掉”的样板。

同时，下列 source model 也并不是 runtime model 的简单别名：

- `ScenarioLocationSource`
- `ScenarioObjectSource`
- `ScenarioSkillSource`
- `ScenarioInitialWorldState`

所以这次重构不应尝试：

- 合并 authoring schema 和 runtime model
- 扁平化 `initial_world_state`
- 用 `Location` / `WorldObject` 直接承接 authored YAML

## 建议范围

本次只做一件事：

### 复用稳定叶子模型

把以下 source model 从 `scenario/schema.py` 中移除：

- `ScenarioAgentStateSource`
- `ScenarioActionCostSource`
- `ScenarioObjectActionEffectSource`
- `ScenarioEventRuleSource`
- `ScenarioTerminationConfigSource`

改为在 schema 中直接引用：

- `AgentState`
- `ActionCost`
- `ObjectActionEffect`
- `WorldEventRule`
- `TerminationConfig`

这样做的前提是逐个确认这些 runtime model 适合承接严格输入校验。

## 明确保留的边界

以下模型继续保留在 `scenario/schema.py`：

### `ScenarioLocationSource`

原因：

- authored YAML 不应接受 `object_ids`
- runtime `Location` 需要持有 loader 组装后的 `object_ids`

### `ScenarioObjectSource`

原因：

- authored schema 支持 `resource_file`
- runtime `WorldObject` 只有 `resource_content`
- `actionable` 需要在加载期补全

### `ScenarioSkillSource`

原因：

- authored skill 是文件引用
- runtime `Skill` 是已解析内容

### `ScenarioInitialWorldState`

原因：

- 它是 authoring 层的结构容器
- 改它的收益太小，不值得引入 YAML 兼容成本

## 对 loader 的影响

这次收缩版重构后，loader 仍应保持显式装配：

- `_build_locations()` 继续构造 runtime `Location`
- `_build_objects()` 继续处理 `resource_file`、`actionable` 和 `object_ids`
- `_build_skills()` 继续解析技能文件
- `_build_world_state()` 继续负责最终 runtime state 组装

变化只应体现在：

- 不再调用一批机械式 `to_xxx()`
- 对可直接复用的叶子模型改用 `model_copy(deep=True)` 或显式构造

## 不建议顺手做的事

以下内容都不应并入这个 PR：

- 重写 `ScenarioObjectSource`
- 扁平化 `initial_world_state`
- 调整 YAML authoring 格式
- 让 loader 直接 `model_dump()` 整体拼 `WorldState`
- 给 `engine.state` 所有模型统一加严格配置

这会把一个低风险清理任务重新放大成结构性重构。

## 建议实施顺序

1. 先只替换 5 个镜像 leaf model。
2. 在 `ScenarioConfig` 和 `ScenarioObjectSource` 中改为引用共享叶子类型。
3. 在 `scenario/loader.py` 中移除对应的 `to_xxx()` 调用。
4. 保持 `ScenarioLocationSource`、`ScenarioObjectSource`、`ScenarioSkillSource` 不动。
5. 运行 `tests/test_scenario_loader.py` 和相关集成测试确认行为不变。

## 验收标准

- `scenario/schema.py` 中删除 5 个低价值镜像模型
- authored YAML 完全兼容现有场景
- loader 仍然清楚地区分“输入校验”和“runtime 组装”
- `demo_town`、`phase1_town` 加载结果不变
- `tests/test_scenario_loader.py` 全部通过

## 优先级建议

这项工作值得做，但优先级低于：

- `engine/actions.py` 拆分
- `TransitionEngine` 进一步模块化

它更适合作为一次小型清理 PR，在主线重构之间穿插完成。
