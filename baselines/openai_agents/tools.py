from __future__ import annotations

from inspect import Parameter, Signature
from typing import Any, Callable

from engine.actions import ActionSpec, ActionToolSpec, TOOL_ACTION_SPECS
from engine.action_models import Action
from runtime.env import TownBenchEnv
from baselines.openai_agents.rendering import RenderMode, render_tool_result

ToolDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]


def build_townbench_tools(
    env: TownBenchEnv,
    *,
    function_tool_decorator: ToolDecorator | None = None,
    output_format: RenderMode = "text",
) -> list[Callable[..., Any]]:
    decorator = function_tool_decorator or _load_function_tool_decorator()
    return [_build_tool(spec, env, decorator, output_format=output_format) for spec in TOOL_ACTION_SPECS]


def _build_tool(
    spec: ActionSpec,
    env: TownBenchEnv,
    decorator: ToolDecorator,
    *,
    output_format: RenderMode,
) -> Callable[..., Any]:
    tool_spec = spec.tool
    if tool_spec is None:
        raise ValueError(f"Action `{spec.action_type}` is not exposed as a baseline tool.")

    def tool(*args: Any, **kwargs: Any) -> str | dict[str, Any]:
        action = _build_action(tool_spec, args=args, kwargs=kwargs)
        return render_tool_result(action, env.step(action), mode=output_format)

    tool.__name__ = tool_spec.name
    tool.__qualname__ = tool_spec.name
    tool.__doc__ = tool_spec.description
    tool.__signature__ = Signature(
        parameters=[
            Parameter(parameter.name, kind=Parameter.POSITIONAL_OR_KEYWORD, annotation=parameter.annotation)
            for parameter in tool_spec.parameters
        ],
        return_annotation=str | dict[str, Any],
    )
    tool.__annotations__ = {
        parameter.name: parameter.annotation
        for parameter in tool_spec.parameters
    } | {"return": str | dict[str, Any]}
    return decorator(tool)


def _build_action(tool_spec: ActionToolSpec, *, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Action:
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
