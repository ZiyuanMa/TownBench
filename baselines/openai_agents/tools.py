from __future__ import annotations

from inspect import Parameter, Signature
from typing import Any, Callable, Optional

from engine.actions import ActionSpec, ActionToolSpec, TOOL_ACTION_SPECS
from runtime.env import TownBenchEnv

ToolDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]


def build_townbench_tools(
    env: TownBenchEnv,
    *,
    function_tool_decorator: Optional[ToolDecorator] = None,
) -> list[Callable[..., Any]]:
    decorator = function_tool_decorator or _load_function_tool_decorator()
    return [_build_tool(spec, env, decorator) for spec in TOOL_ACTION_SPECS]


def _serialize_step_result(result: Any) -> dict[str, Any]:
    return result.model_dump()


def _build_tool(spec: ActionSpec, env: TownBenchEnv, decorator: ToolDecorator) -> Callable[..., Any]:
    tool_spec = spec.tool
    if tool_spec is None:
        raise ValueError(f"Action `{spec.action_type}` is not exposed as a baseline tool.")

    def tool(*args: Any, **kwargs: Any) -> dict[str, Any]:
        action = _build_action(tool_spec, args=args, kwargs=kwargs)
        return _serialize_step_result(env.step(action))

    tool.__name__ = tool_spec.name
    tool.__qualname__ = tool_spec.name
    tool.__doc__ = tool_spec.description
    tool.__signature__ = Signature(
        parameters=[
            Parameter(parameter.name, kind=Parameter.POSITIONAL_OR_KEYWORD, annotation=parameter.annotation)
            for parameter in tool_spec.parameters
        ],
        return_annotation=dict[str, Any],
    )
    tool.__annotations__ = {
        parameter.name: parameter.annotation
        for parameter in tool_spec.parameters
    } | {"return": dict[str, Any]}
    return decorator(tool)


def _build_action(tool_spec: ActionToolSpec, *, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if args and kwargs:
        raise TypeError(f"{tool_spec.name} accepts either positional or keyword arguments, not both.")
    if args:
        return tool_spec.build_action(*args)
    return tool_spec.build_action(**kwargs)


def _load_function_tool_decorator() -> ToolDecorator:
    try:
        from agents import function_tool
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI baseline."
        ) from exc
    return function_tool
