# TownBench 架构说明

## 项目定位

TownBench 是一个面向 LLM Agent 的基准测试环境。它模拟一个虚拟小镇，Agent
通过工具调用（move、inspect、call_action 等）与环境交互，完成经济活动任务。
环境以 YAML 场景文件驱动，支持可插拔的 baseline agent 实现。

## 分层架构

```
┌─────────────────────────────────────────────┐
│  scripts/          CLI 入口                  │
├─────────────────────────────────────────────┤
│  baselines/        Agent 实现（OpenAI Agents）│
├─────────────────────────────────────────────┤
│  runtime/          环境封装（TownBenchEnv）    │
├─────────────────────────────────────────────┤
│  engine/           核心引擎                   │
│   ├─ state.py       世界状态模型               │
│   ├─ actions.py     动作定义 + handler        │
│   ├─ transition.py  转换引擎（step 执行管线）   │
│   ├─ rules.py       时间、事件、终止规则        │
│   ├─ observation.py 观测投影（Agent 可见数据）   │
│   ├─ results.py     StepResult（返回给 Agent） │
│   └─ trace.py       TraceEntry（内部审计日志）  │
├─────────────────────────────────────────────┤
│  scenario/         场景加载                   │
│   ├─ schema.py      YAML 输入校验模型          │
│   └─ loader.py      加载 + 验证 + 组装         │
├─────────────────────────────────────────────┤
│  evaluation/       评分                      │
│   └─ scorer.py      EpisodeScore 计算         │
├─────────────────────────────────────────────┤
│  scenarios/        场景内容（YAML + 资源文件）   │
│  tests/            pytest 测试                │
└─────────────────────────────────────────────┘
```

**依赖方向**：`baselines → runtime → engine ← scenario`，`evaluation → engine`。
不存在循环依赖。

## 核心数据流

```
scenario.yaml
     │  load_scenario()
     ▼
 WorldState ──── TownBenchEnv.reset() ────▶ Observation
     │                                         │
     │  Agent 发出 Action (tool call)           │ 返回给 Agent
     ▼                                         │
TransitionEngine.step()                        │
     │                                         │
     ├─ 1. normalize_action()   解析+校验       │
     ├─ 2. handler(state)       执行动作逻辑     │
     ├─ 3. apply_action_costs() 扣除时间/能量    │
     ├─ 4. apply_world_rules()  触发事件规则     │
     ├─ 5. evaluate_termination() 检查终止条件   │
     ▼                                         │
TransitionOutcome                              │
     ├─ new WorldState                         │
     ├─ StepResult ────────────────────────────┘
     └─ TraceEntry  (内部日志)
```

## 关键模型

### WorldState (`engine/state.py`)

环境的完整内部状态，包含：

- `agent: AgentState` — 位置、金钱、能量、背包、笔记
- `locations: dict[str, Location]` — 地图节点及连接
- `objects: dict[str, WorldObject]` — 可交互物体及其动作效果
- `skills: dict[str, Skill]` — 可加载的技能文档
- `world_flags: dict[str, bool]` — 全局状态标志
- `event_rules` — 当 world_flags 满足条件时自动触发的规则
- `termination_config` — max_steps、能量耗尽、成功/失败 flag

### Action 与 ActionSpec (`engine/actions.py`)

7 种内置动作类型：`move_to` / `inspect` / `open_resource` / `load_skill` /
`check_status` / `write_note` / `call_action`。

每种动作通过 `ActionSpec` 注册：
- `handler` — 执行逻辑函数
- `tool` — `ActionToolSpec`（名称、描述、参数、builder），用于自动生成 baseline 工具
- `default_cost` — 默认时间/能量消耗（可被场景覆盖）

`call_action` 是最通用的动作——它调用 `WorldObject` 上暴露的自定义 action，
支持前置条件检查（world_flags、inventory、money）和副作用（状态变更、传送等）。

### Observation (`engine/observation.py`)

Agent 可见的信息切片，**不暴露**完整 WorldState。仅包含：
- 当前位置信息和连接
- 当前位置的可见物体（名称、摘要、visible_state、action_ids）
- 可用技能列表（仅 id + 名称 + 描述，不含完整 content）
- Agent 自身状态

### TransitionEngine (`engine/transition.py`)

无状态的转换引擎。`step()` 方法：
1. Deep copy 输入 state（保证不可变语义）
2. 执行 action handler
3. 成功时扣除 action cost
4. 运行世界事件规则
5. 检查终止条件
6. 返回 `TransitionOutcome`（新 state + StepResult + TraceEntry）

### TownBenchEnv (`runtime/env.py`)

对 TransitionEngine 的有状态封装，提供 `reset()` / `step()` / `get_trace()`
/ `is_done()` 接口。类似 Gymnasium 环境的 API 风格。

## 场景系统 (`scenario/`)

场景以 YAML 定义，包含：地图、物体、技能文件引用、动作消耗覆盖、世界事件规则、
终止条件。`loader.py` 在加载时执行严格校验：

- 唯一性检查（location/object/skill/event ID）
- 引用完整性（links 指向已知 location、object 在已知 location）
- action_effects 不允许存在未暴露的动作
- event_rules 不允许引用未知 object
- 技能文件必须有 YAML frontmatter（name + description）

## Baseline 系统 (`baselines/`)

### 抽象层 (`baselines/base.py`)

提供 `resolve_episode_env()`、`build_episode_initial_input()`、
`build_episode_result()` 等通用函数，不依赖具体 Agent 框架。

### OpenAI Agents 实现 (`baselines/openai_agents/`)

- `tools.py` — 从 `TOOL_ACTION_SPECS` 动态生成带签名的 Python 函数，
  用 `@function_tool` 装饰后交给 OpenAI Agents SDK
- `agent.py` — 构造 Agent 实例（可注入自定义 agent_cls 和 tool decorator）
- `runner.py` — 同步和流式两种运行模式，处理 `MaxTurnsExceeded` 异常
- `config.py` — 配置（模型、max_turns、API 模式），支持环境变量

## 评分 (`evaluation/scorer.py`)

当前评分指标：
- `survived_days` — 存活天数
- `final_money` — 最终金钱
- `step_count` — 总步数
- `done` / `termination_reason` — 终止状态

## 测试结构 (`tests/`)

- `conftest.py` — 提供 `minimal_world_state` fixture
- `test_actions.py` — ActionSpec 注册表和 cost 逻辑
- `test_transition.py` — 转换引擎的完整行为测试
- `test_observation.py` — 观测投影和数据隔离
- `test_trace.py` — Trace 记录正确性
- `test_env.py` — TownBenchEnv 封装
- `test_scorer.py` — 评分计算
- `test_scenario_loader.py` — 场景加载和所有校验规则
- `test_phase1_scenario.py` — phase1_town 场景的集成测试
- `test_openai_baseline.py` — Baseline 工具和 runner（使用 Fake 替身）
