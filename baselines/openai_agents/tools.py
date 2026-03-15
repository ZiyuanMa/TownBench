from __future__ import annotations

from typing import Any, Callable, Optional

from runtime.env import TownBenchEnv

ToolDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]


def build_townbench_tools(
    env: TownBenchEnv,
    *,
    function_tool_decorator: Optional[ToolDecorator] = None,
) -> list[Callable[..., Any]]:
    decorator = function_tool_decorator or _load_function_tool_decorator()

    @decorator
    def move_to(target_id: str) -> dict[str, Any]:
        """Move the agent to a linked location by location id."""
        return _serialize_step_result(env.step({"type": "move_to", "target_id": target_id}))

    @decorator
    def inspect(target_id: str) -> dict[str, Any]:
        """Inspect the current location or an object that is present there."""
        return _serialize_step_result(env.step({"type": "inspect", "target_id": target_id}))

    @decorator
    def open_resource(target_id: str) -> dict[str, Any]:
        """Open a readable resource in the current location and return its content."""
        return _serialize_step_result(env.step({"type": "open_resource", "target_id": target_id}))

    @decorator
    def load_skill(target_id: str) -> dict[str, Any]:
        """Load a skill document by skill id."""
        return _serialize_step_result(env.step({"type": "load_skill", "target_id": target_id}))

    @decorator
    def check_status() -> dict[str, Any]:
        """Check the agent status, including location, money, energy, inventory and notes."""
        return _serialize_step_result(env.step({"type": "check_status"}))

    @decorator
    def write_note(text: str) -> dict[str, Any]:
        """Write a note into the agent's notebook."""
        return _serialize_step_result(env.step({"type": "write_note", "args": {"text": text}}))

    @decorator
    def call_action(target_id: str, action_name: str) -> dict[str, Any]:
        """Call an exposed action on an object in the current location."""
        return _serialize_step_result(
            env.step({"type": "call_action", "target_id": target_id, "args": {"action": action_name}})
        )

    return [move_to, inspect, open_resource, load_skill, check_status, write_note, call_action]


def _serialize_step_result(result: Any) -> dict[str, Any]:
    return result.model_dump()


def _load_function_tool_decorator() -> ToolDecorator:
    try:
        from agents import function_tool
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI baseline."
        ) from exc
    return function_tool
