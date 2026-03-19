# 重构提案：拆分 actions.py

## 问题描述

`engine/actions.py` 目前有 **472 行**，承担了 5 种不同职责：

| 职责 | 行数（约） | 内容 |
|------|-----------|------|
| 数据模型 | ~30 | `Action`, `ActionType`, `ActionExecution` |
| Spec 注册体系 | ~40 | `ActionSpec`, `ActionToolSpec`, `ActionToolParameter` |
| Handler 实现 | ~200 | `_handle_move_to`, `_handle_inspect`, ... (8 个) |
| Action Builder | ~30 | `_build_move_to_action`, ... (8 个) |
| Spec 注册表 + 辅助 | ~70 | `ACTION_SPECS`, `get_action_cost`, `_serialize_*` |

Handler 实现占了接近一半的代码量，且逻辑各自独立。随着新 action 类型的添加
（如规划中的 `trade`, `craft` 等），这个文件会持续膨胀。

---

## 推荐方案：拆分为 actions + handlers

### 目标文件结构

```
engine/
├── actions.py      # 数据模型 + Spec 注册体系 + 注册表（~150 行）
├── handlers.py     # 所有 _handle_* 函数 + 辅助函数（~250 行）
├── ...
```

### actions.py 保留内容

```python
# engine/actions.py
from engine.handlers import (
    handle_check_status,
    handle_move_to,
    handle_inspect,
    handle_write_note,
    handle_search,
    handle_open_resource,
    handle_load_skill,
    handle_call_action,
)

# --- 数据模型 ---
ActionType = Literal[...]

class Action(BaseModel): ...
class ActionExecution: ...

# --- Spec 体系 ---
class ActionToolParameter: ...
class ActionToolSpec: ...
class ActionSpec: ...

# --- 注册表 ---
_ACTION_SPEC_LIST: tuple[ActionSpec, ...] = (
    ActionSpec(
        action_type="move_to",
        default_cost=ActionCost(time_delta=10, energy_delta=-2),
        tool=ActionToolSpec(
            name="move_to",
            description="Move the agent to a linked location by location id.",
            parameters=(ActionToolParameter("target_id"),),
            build_action=lambda target_id: Action(type="move_to", target_id=target_id),
        ),
        handler=handle_move_to,
    ),
    # ...
)

ACTION_SPECS: dict[str, ActionSpec] = ...
TOOL_ACTION_SPECS: tuple[ActionSpec, ...] = ...

# --- 公开 API ---
def normalize_action(...) -> Action: ...
def get_action_spec(...) -> ActionSpec | None: ...
def get_action_cost(...) -> ActionCost: ...
def apply_action_costs(...) -> ActionCost: ...
```

### handlers.py 新文件内容

```python
# engine/handlers.py
"""Action handler implementations for all built-in action types."""

from engine.state import ActionCost, WorldObject, WorldState

# 注意：不导入 actions 模块，避免循环依赖
# ActionExecution 和 Action 通过参数传入

def handle_move_to(state, action):
    """Move agent to a linked location."""
    ...

def handle_inspect(state, action):
    """Inspect the current location or accessible object."""
    ...

def handle_call_action(state, action):
    """Execute an exposed object action with full validation."""
    ...

# --- 辅助函数 ---
def _get_accessible_object(state, target_id): ...
def _serialize_object(world_object): ...
def _serialize_agent_status(state): ...
def _has_required_inventory(state, required_inventory): ...
def _can_apply_inventory_delta(state, inventory_delta): ...
```

### 依赖方向

```
transition.py → actions.py → handlers.py → state.py
                    ↓              ↓
                 rules.py       rules.py
```

关键约束：`handlers.py` 只依赖 `state.py` 和 `rules.py`，**不回依赖
`actions.py`**。`ActionExecution` 类型需要从 `actions.py` 导入，但这是
单向依赖，不会造成循环。

### 循环依赖规避

`handlers.py` 需要使用 `ActionExecution` 和 `Action` 类型。处理方式：

```python
# engine/handlers.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.actions import Action, ActionExecution

# 实际运行时通过函数签名接收，不直接导入模块
# 或者将 ActionExecution 移至 state.py 或独立的 types.py
```

更干净的替代方案：将 `Action` 和 `ActionExecution` 移至 `engine/types.py`，
两个模块都从 `types.py` 导入。

---

## 额外优化：内联 `_build_*_action` 函数

当前 8 个 `_build_*_action` 函数都是简单的单行构造：

```python
# 当前（8 个独立函数，~30 行）
def _build_move_to_action(target_id: str) -> Action:
    return Action(type="move_to", target_id=target_id)

def _build_inspect_action(target_id: str) -> Action:
    return Action(type="inspect", target_id=target_id)
# ...
```

拆分后直接内联到 Spec 注册表的 lambda 中：

```python
ActionToolSpec(
    name="move_to",
    build_action=lambda target_id: Action(type="move_to", target_id=target_id),
    ...
),
```

消除 ~30 行样板代码。

---

## 预期效果

| 指标 | 当前 | 重构后 |
|------|------|--------|
| `actions.py` 行数 | 472 | ~150 |
| `handlers.py` 行数 | — | ~250 |
| 最大单文件复杂度 | 高 | 中 |
| 新增 action 需修改的文件 | 1 个大文件 | 2 个小文件 |
| builder 函数数 | 8 | 0（内联） |

## 风险

- `engine/__init__.py` 的公开 API 不变，外部调用者无感知。
- `handlers.py` 和 `actions.py` 之间的类型依赖需要仔细管理。
- 测试文件 `test_actions.py` 可能需要调整导入路径。

## 建议验证步骤

1. 创建 `engine/handlers.py`，移入所有 `_handle_*` 函数和辅助函数。
2. 更新 `actions.py` 导入 handler 引用。
3. 内联所有 `_build_*_action` 函数。
4. 运行 `pytest` 全量测试确认不破坏行为。
5. 检查 `engine/__init__.py` 的公开 API 仍然一致。
