# 重构提案：拆分 `engine/actions.py`

## 结论

这个重构是合理的，但目标应该收敛为：

- 降低 `engine/actions.py` 的阅读负担
- 把 action handler 实现与 action 注册信息分开
- 保持现有外部 API、行为顺序和测试语义不变

不建议把它表述成“重新设计 action 系统”。从当前代码看，注册表、默认 cost、tool 元数据、handler 引用已经收敛在同一个 `ActionSpec` 里，核心问题不是“多处注册”，而是**一个文件同时承载了模型、注册表、handler 实现和若干私有辅助逻辑**。

## 当前现状

`engine/actions.py` 目前同时包含：

- action 输入模型：`Action`
- action 执行结果模型：`ActionExecution`
- tool/spec 注册结构：`ActionToolSpec`、`ActionSpec`
- 所有内建 `_handle_*` 实现
- 若干仅供 handler 使用的私有辅助函数
- action registry 与默认 cost 查询逻辑

当前实现里已经有两个值得保留的点：

1. `ActionSpec` 已经同时持有 `default_cost`、`tool`、`handler`
2. `TransitionEngine` 已经通过 `get_action_spec()` 做 dispatch，而不是维护独立 handler map

所以这次重构不需要再引入新的 registry 机制，也不需要改变 `TransitionEngine` 的公开协作方式。

## 真正的问题

当前文件的问题主要是模块职责混杂，而不是注册表分散：

- handler 实现占据了文件的大部分阅读空间
- `_get_accessible_object()`、`_serialize_object()`、`_has_required_inventory()` 这类私有 helper 只服务于 handler，却和 registry 紧耦合在同一文件
- 新增 action 时，虽然理论上只需改一个文件，但这个文件已经同时承担“定义”和“实现”，评审成本会继续升高

此外，`call_action` handler 本身包含较多校验和状态写入逻辑，继续往这个文件里堆新动作会让 `actions.py` 越来越像“半个 transition 子系统”。

## 推荐方案

### 目标结构

```text
engine/
├── action_models.py    # Action / ActionExecution / 相关 type alias
├── action_handlers.py  # 所有内建 handler 与私有 helper
├── actions.py          # ActionSpec / registry / normalize_action / get_action_cost
```

### 设计原则

- `actions.py` 保留“声明式定义”
- `action_handlers.py` 只放“行为实现”
- 共享的数据结构放到独立模块，避免循环依赖
- `engine.actions` 继续作为对外入口，必要时 re-export 现有符号

## 为什么不建议只拆成 `actions.py + handlers.py`

如果 `actions.py` import `handlers.py` 来组装 registry，而 `handlers.py` 又需要运行时使用 `Action` 和 `ActionExecution`，那么仅靠 `TYPE_CHECKING` 不够，因为 handler 需要真正构造 `ActionExecution` 实例。

因此更稳妥的最小方案是先把共享模型抽到独立模块：

- `Action`
- `ActionExecution`
- `ActionType`
- `ActionHandler`
- `PayloadBuilder`

这样依赖方向会变成：

```text
transition.py -> actions.py -> action_handlers.py
                  |               |
                  v               v
             action_models.py   action_models.py
```

这比“handlers 不能回依赖 actions，但又要直接使用 actions 里的运行时类型”更自洽。

## 拆分后各文件职责

### `engine/action_models.py`

保留纯数据定义：

- `ActionType`
- `Action`
- `ActionExecution`
- `PayloadBuilder`
- `ActionHandler`

这部分不应感知 registry、tool spec 或 engine rules。

### `engine/action_handlers.py`

迁移以下内容：

- `_handle_move_to`
- `_handle_inspect`
- `_handle_open_resource`
- `_handle_load_skill`
- `_handle_check_status`
- `_handle_write_note`
- `_handle_call_action`
- `_success` / `_failure`
- `_get_accessible_object`
- `_serialize_object`
- `_serialize_agent_status`
- `_has_required_inventory`
- `_can_apply_inventory_delta`

这个模块可以依赖：

- `engine.action_models`
- `engine.rules`
- `engine.state`

但不应该知道 registry 的存在。

### `engine/actions.py`

保留注册与查询入口：

- `ActionSpec`
- `ActionToolSpec`
- `ActionToolParameter`
- `_ACTION_SPEC_LIST`
- `ACTION_SPECS`
- `TOOL_ACTION_SPECS`
- `normalize_action()`
- `get_action_spec()`
- `get_action_cost()`
- `apply_action_costs()`

同时 re-export：

- `Action`
- `ActionExecution`
- `ActionType`

这样可以最大限度保持：

- `engine/__init__.py`
- `runtime/env.py`
- `baselines/openai_agents/tools.py`
- 现有测试

的导入路径稳定。

## 不建议顺手做的事

这次重构不建议混入以下变化：

- 修改 action 名称或 tool 协议
- 调整 `ActionSpec` 结构
- 修改 `TransitionEngine` 的 step 顺序
- 重写 `call_action` 业务规则
- 改动 baseline tool 生成逻辑

这些都属于行为层面的变化，不应和“拆文件”混在同一个 PR 里。

## 风险

### 1. 循环依赖

这是首要风险。没有共享模型模块时，`actions.py <-> handlers.py` 很容易形成真实循环。

缓解方式：

- 先抽 `action_models.py`
- 再迁移 handlers
- 最后让 `actions.py` 组装 registry 并做 re-export

### 2. 私有 helper 迁移后行为漂移

`_serialize_object()` 和 `_serialize_agent_status()` 会影响 step payload；`_has_required_inventory()` 和 `_can_apply_inventory_delta()` 会影响失败分支。

缓解方式：

- 迁移前先锁定现有测试
- 如有必要，补充针对 payload 与 warning code 的直接测试

### 3. 外部导入路径回归

当前已有代码直接从 `engine.actions` 导入符号，测试也覆盖了这一点。

缓解方式：

- 在 `engine.actions` 中保留原有导出
- 若新增 `action_models.py`，也不要要求外部调用方立即切换导入

## 建议实施顺序

1. 新建 `engine/action_models.py`，先搬运纯数据结构与 type alias。
2. 更新 `engine/actions.py`，改为从 `action_models.py` 导入这些类型，并保持原有导出。
3. 新建 `engine/action_handlers.py`，迁移所有 `_handle_*` 和私有 helper。
4. 在 `engine/actions.py` 中引用新的 handler 函数来构建 `_ACTION_SPEC_LIST`。
5. 运行 `tests/test_actions.py`、`tests/test_transition.py` 和 baseline 相关测试。
6. 最后再考虑是否要对 `TransitionEngine` 做更细的 pipeline 拆分；那应是下一阶段，不是本次拆分的一部分。

## 验收标准

- `engine.actions` 仍然是 action 注册与查询的唯一对外入口
- 现有 action 行为、warning code、payload 结构不变
- `TransitionEngine` 无需改动其公开接口
- 新增一个内建 action 时，注册信息与实现位置清晰且职责分离
- `tests/test_actions.py` 与 `tests/test_transition.py` 全部通过

## 总结

这份重构值得做，但应把目标定为**清理模块边界**，而不是重新发明 action 架构。

最稳妥的落地方式不是简单地把 handler 挪去另一个文件，而是先抽出共享 action 模型，再完成 handler 拆分，并通过 `engine.actions` 维持兼容的公开入口。
