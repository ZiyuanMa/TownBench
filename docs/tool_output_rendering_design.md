# Tool Output Rendering Design

## 背景

当前 TownBench 的 OpenAI Agents baseline 在 agent 与环境交互时，直接把
`StepResult` 整体序列化为 JSON 后返回给 tool caller。

这带来两个直接问题：

- agent 看到的是大段结构化 JSON，而不是更适合语言模型消费的自然语言反馈
- 不同 tool 的结果被统一包进同一种通用结构，语义差异没有在输出层体现出来

这个问题不只影响模型，也影响人类调试体验。流式运行时，CLI 目前也会把
tool output 原样打印出来，因此终端中出现的往往也是原始 JSON 串。

## 当前实现

当前链路大致如下：

1. `engine/transition.py` 生成结构化 `StepResult`
2. `baselines/openai_agents/tools.py` 直接对 `StepResult` 调用 `model_dump()`
3. OpenAI Agents SDK 把这个结果作为 tool output 反馈给模型
4. `baselines/openai_agents/runner.py` 在流式模式下把 tool output 原样转发给 CLI
5. `scripts/run_openai_baseline.py` 将该事件直接打印到 stderr

需要注意的是，问题主要出在 baseline 的输出层，而不是 engine 完全缺少语义。

底层其实已经有较好的动作语义基础：

- `StepResult.message` 已经是动作级自然语言
- `StepResult.data` 会按动作类型提供不同 payload
- `engine/action_handlers.py` 中已经区分了 `status`、`object`、`resource`、`skill`、`action` 等语义

因此，这次设计的重点不是重写状态机，而是补一层面向 agent 的输出渲染。

## 问题拆解

### 1. 输出过于结构化

当前 tool output 通常包含：

- `success`
- `message`
- 完整 `observation`
- 时间、金钱、能量、库存变化
- `warnings`
- `done`
- `termination_reason`
- `data`

这使得一次很简单的动作，例如 `move_to("workshop")`，也会返回一整份当前环境快照。
模型当然可以从 JSON 中提取关键信息，但这并不是最省 token、最省推理负担的接口。

### 2. 不同 tool 的语义没有在展示层体现

目前 `move_to`、`inspect`、`check_status`、`open_resource`、`load_skill`、
`call_action` 都通过同一个通用 JSON 包返回。

但这些工具的理想反馈并不相同：

- `move_to` 更关心“我到了哪里，现在能去哪里，看到了什么”
- `check_status` 更关心“当前时间、位置、金钱、能量、库存、笔记”
- `inspect` 更关心目标详情和可用动作
- `open_resource` / `load_skill` 更关心正文内容
- `call_action` 更关心动作效果、资源变化和触发事件

统一返回完整 observation，会把真正重要的信息淹没掉。

### 3. 人类可读性差

流式运行时打印的 `tool_output` 现在是 JSON，这对快速观察 agent 的决策链很不友好。
终端里最有价值的信息其实是：

- tool 调用了什么
- 调用是否成功
- 关键状态发生了什么变化
- 下一步可能可做什么

这些信息应该直接可读，而不是必须靠人眼去扫 JSON。

## 设计目标

这次改动的目标是：

1. 让 agent 默认接收到自然语言形式的 tool 输出
2. 让不同 tool 按其语义返回不同密度、不同类型的信息
3. 保持 `engine`、`runtime`、`trace`、`evaluation` 内部结构化结果不变
4. 让流式日志复用同一套渲染逻辑，提升人类调试体验
5. 保留调试和回溯所需的结构化信息出口

## 非目标

这次设计不打算做以下事情：

1. 不重构 `StepResult`、`TraceEntry` 或环境内部状态模型
2. 不改变 action 语义、world rules 或 scenario schema
3. 不移除最终 episode 结果的 JSON 输出
4. 不引入新的 action 类型
5. 不在第一步就重做整个 runner 事件系统

## 核心设计原则

### 1. 结构化结果保留在 engine，渲染发生在 baseline

`StepResult` 仍然应该是内部的 canonical result。

原因：

- trace 和评估依赖结构化字段
- 测试需要直接断言 delta、warning、done 等字段
- engine 的职责是定义环境语义，而不是定义面向某个 agent SDK 的展示文案

因此，渲染层应该放在 `baselines/`，而不是 `engine/`。

### 2. agent 看到的是“可行动文本”，不是“完整状态转储”

agent tool output 的目标不是保真还原所有内部字段，而是帮助模型决定下一步动作。

这意味着输出应该遵循：

- 优先给出动作结果
- 只给出与该 tool 决策相关的上下文
- 默认避免重复整个 observation
- 在需要完整正文时保留全文，例如资源和技能文档

### 3. 人类调试与模型消费使用同一套语义

tool 输出一旦转成自然语言，流式日志不应再单独维护另一套描述。

否则会出现：

- agent 看到一种表达
- 人类看到另一种表达
- 两边难以对应，调试成本上升

因此应尽量让 CLI 和 agent 复用同一套 renderer。

## 方案总览

建议新增一层 baseline presentation module，例如：

- `baselines/openai_agents/rendering.py`

该模块负责两类事情：

1. 将 `StepResult` 渲染为 agent 可消费的 tool output
2. 将初始 observation 渲染为自然语言开场描述

建议提供以下接口：

```python
def render_tool_result(action_type: str, result: StepResult, *, mode: str = "text") -> str | dict[str, Any]:
    ...


def render_initial_observation(observation: Observation | dict[str, Any]) -> str:
    ...
```

其中：

- `mode="text"` 为默认模式
- `mode="json"` 作为调试或兼容模式保留

## Tool 输出设计

### 通用输出骨架

所有 tool 的文本输出都建议包含以下层次：

1. 动作结果句
2. 关键资源变化
3. 动作特有上下文
4. 若 episode 已结束，则附加终止信息

通用信息应简短，避免机械重复。

例如资源变化可只在非零时出现：

- `Time: Day 1, 08:26 (+10m).`
- `Money: 21 (+9).`
- `Energy: 92 (-4).`
- `Inventory: tea_box +1.`

### `move_to`

目标：帮助模型快速建立局部环境上下文。

建议返回：

- 是否成功移动
- 新地点名称和 id
- 当前可见对象简表
- 附近可到达地点
- 时间/能量变化

不建议返回：

- 完整 agent 状态
- 所有 skill 详情
- 完整 observation JSON

示例：

```text
Moved to Workshop (`workshop`).
Time: Day 1, 08:12 (+12m). Energy: 97 (-3).
Visible here: Tea Station (`brew_tea`), Storage Shelf, Completion Log (`record_order`).
Nearby locations: plaza.
```

失败时建议附带最有用的纠错信息：

- 当前位置
- 当前可达地点

### `inspect`

目标：让模型理解目标对象或地点的公开属性。

建议返回：

- inspect 成功与否
- 目标名称、类型、summary
- `visible_state`
- 公开 `action_ids`

示例：

```text
Inspected Tea Station (`tea_station`).
Summary: A station that can brew tea for pickup.
Visible state: brewed_today=false.
Available actions: brew_tea.
Time: Day 1, 08:16 (+4m). Energy: 96 (-1).
```

### `check_status`

目标：提供完整但紧凑的 agent 状态摘要。

建议返回：

- 当前时间
- 当前位置
- money / energy
- inventory
- notes 数量或简表
- stats
- status_effects

示例：

```text
Status checked.
Time: Day 1, 08:12.
Location: workshop.
Money: 12. Energy: 97.
Inventory: empty.
Notes: none.
Stats: none.
```

### `open_resource`

目标：保留文档正文，而不是重复环境状态。

建议返回：

- 资源标题
- 资源对象 id
- 正文全文
- 可选的简短前缀说明

示例：

```text
Opened resource Tea Ledger (`tea_ledger`).
Content:
...
```

这里不建议截断正文，因为资源正文往往就是决策所需的信息本体。

### `load_skill`

与 `open_resource` 类似，但应保留 skill 的名称、描述和全文。

示例：

```text
Loaded skill Tea Basics (`tea_basics`).
Description: Basic workshop tea preparation steps.
Content:
...
```

### `write_note`

目标：确认副作用已生效，不重复无关上下文。

建议返回：

- 保存成功与否
- 最新 note 文本或 note 总数

示例：

```text
Note saved.
Notebook entries: 3.
Latest note: Brew tea before recording the order.
```

### `call_action`

目标：准确表达环境变化。

建议返回：

- 动作结果句
- money / energy / inventory 变化
- 触发事件
- 与该对象动作直接相关的公开状态变化
- 必要时补充当前位置

示例：

```text
You brewed a fresh pot of tea.
Time: Day 1, 08:26 (+10m). Energy: 92 (-4).
Triggered events: tea_ready_notice.
Tea Station state: brewed_today=true.
Current location: workshop.
```

失败时建议根据错误类型补上下文，例如：

- 缺少 inventory 时指出缺哪些物品
- 动作未暴露时指出该对象当前公开 action 列表
- target 不在当前位置时指出当前位置可交互对象

## 初始 observation 设计

除了每一步 tool output，初始 observation 目前也被直接渲染成 JSON。
这会让 agent 在 episode 开始时就面对一大段结构化数据。

建议将 `build_episode_initial_input()` 的 observation 部分改写为自然语言块。

推荐结构：

1. opening briefing
2. public rules
3. 当前时间和地点
4. 当前 area
5. 可达地点
6. 可见对象列表
7. 可见 skills 列表
8. 自身状态摘要

示例：

```text
Initial observation:
Time: Day 1, 08:00.
Current location: Plaza (`plaza`).
Nearby locations: workshop, market.
Visible objects:
- Bulletin Board: Public notices for local jobs.
Visible skills:
- tea_basics: Basic workshop tea preparation steps.
Agent status:
- Money: 12
- Energy: 100
- Inventory: empty
```

这部分和 tool output 一样，目标是帮助模型快速建立行动上下文，而不是复制内部数据结构。

## 兼容性策略

为了降低切换风险，建议保留一个可选的 JSON 模式。

可选方式包括：

- `OpenAIAgentsConfig.tool_output_format = "text" | "json"`
- CLI 参数 `--tool-output-format`

推荐默认值：

- `text`

保留 JSON 模式的原因：

- 便于对比新旧行为
- 便于低层调试
- 避免一次性切断所有依赖结构化 tool 输出的测试或脚本

最终 episode 结果的 JSON 输出应继续保留，不属于本次改动范围。

## Runner 与 CLI 设计

在第一阶段，建议尽量少改 runner 的接口。

具体建议：

1. tool 函数默认直接返回渲染后的文本
2. `runner.py` 在流式模式下继续透传 `tool_output`
3. `scripts/run_openai_baseline.py` 继续打印事件，但输出内容变成人类可读文本

这意味着：

- agent 看到的是自然语言
- 人在终端里看到的也是自然语言
- 不需要第一步就把 `on_event` 改成更复杂的结构化事件对象

如果后续发现 CLI 对多行事件格式支持不足，再单独重构 stream event API。

## 为什么不直接改 `StepResult`

不建议让 `StepResult` 同时承担：

- 环境内部结果模型
- trace/评估输入
- 面向 agent 的交互文案

这样会让一个模型承载过多职责，并把 baseline 展示层耦合进 engine。

更合理的边界是：

- `engine` 负责产生结构化语义结果
- `baselines` 负责把这些语义结果翻译成适合模型消费的表述

## 测试计划

建议补充三层测试。

### 1. 渲染层单元测试

新增针对 renderer 的直接测试，覆盖：

- `move_to`
- `inspect`
- `check_status`
- `open_resource`
- `load_skill`
- `write_note`
- `call_action`
- 常见失败分支

重点断言：

- 返回文本是否包含关键语义
- 是否省略了不必要的 observation dump
- 是否保留了资源正文和技能全文

### 2. baseline 集成测试

更新 `tests/test_openai_baseline.py`，重点验证：

- 默认模式下 tool 返回字符串而不是 dict
- 字符串中包含关键状态变化
- 若启用 JSON 兼容模式，仍可返回结构化结果

### 3. runner / CLI 行为测试

验证流式事件中：

- `tool_called` 仍能正常出现
- `tool_output` 已变为人类可读文本
- 最终 `BaselineEpisodeResult` 的结构化 JSON 输出保持不变

## 实施顺序

建议按以下顺序落地：

1. 新增 `rendering.py`，先只处理 `StepResult -> text`
2. 接入 `build_townbench_tools()`，让 tool 默认返回文本
3. 更新 baseline 测试
4. 将初始 observation 改成自然语言渲染
5. 调整流式日志展示
6. 在变更完成后更新 `docs/architecture.md`

其中第 4 步可以视实现复杂度独立成第二个提交，但建议仍归属于同一设计方向。

## 风险与缓解

### 风险 1：模型丢失结构化细节

如果文本渲染过于简化，模型可能缺少决策所需上下文。

缓解方式：

- 针对不同 tool 保留最相关的字段
- 对 `open_resource` / `load_skill` 保留全文
- 提供 JSON 兼容模式

### 风险 2：文本模板过长，反而增加 token

如果每个 tool 都写成长段描述，也会造成浪费。

缓解方式：

- 只在字段非空或非零时输出
- 不重复整份 observation
- 不把所有 agent 状态塞进每个动作结果

### 风险 3：测试和已有调用方依赖 dict 返回

目前 baseline 测试直接把 tool 返回值当 dict 使用。

缓解方式：

- 同步更新测试到文本模式
- 提供 JSON 兼容模式，便于过渡

## 开放问题

以下问题建议在实现前确认：

1. `call_action` 失败时是否需要更强的纠错提示，例如直接列出可用动作
2. `move_to` 成功后是否要输出可见 skill 列表，还是只输出对象和地点
3. `open_resource` / `load_skill` 是否始终保留全文，还是允许配置为摘要模式
4. 初始 observation 的自然语言化是否与 tool 输出在同一次改动中完成

## 推荐结论

推荐采用以下默认策略：

1. 保持 `engine` 内部结构化结果不变
2. 在 `baselines/openai_agents/` 新增渲染层
3. 默认让 tool 返回自然语言文本
4. 按不同 tool 类型返回不同的信息密度和关注点
5. 保留 `json` 兼容模式用于调试和回归比较
6. 后续再把初始 observation 一并改成自然语言描述

这个方案的优势是边界清晰、改动集中、兼容性可控，也最符合当前代码结构。
