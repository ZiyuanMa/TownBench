from __future__ import annotations

from inspect import Parameter, Signature
from typing import Any, Callable

from engine.actions import ActionSpec, ActionToolSpec, TOOL_ACTION_SPECS
from engine.action_models import Action
from engine.rendering import render_tool_result
from runtime.env import TownBenchEnv

ToolFactory = Callable[[Callable[..., Any]], Any]


def build_townbench_tools(
    env: TownBenchEnv,
    *,
    tool_factory: Callable[..., Any] | None = None,
) -> list[Any]:
    factory = tool_factory or _load_tool_factory()
    return [_build_tool(spec, env, factory) for spec in TOOL_ACTION_SPECS]


def _build_tool(
    spec: ActionSpec,
    env: TownBenchEnv,
    factory: Callable[..., Any],
) -> Any:
    tool_spec = spec.tool
    if tool_spec is None:
        raise ValueError(f"Action `{spec.action_type}` is not exposed as an agent tool.")

    def tool(*args: Any, **kwargs: Any) -> str:
        action = _build_action(tool_spec, args=args, kwargs=kwargs)
        return render_tool_result(action, env.step(action))

    tool.__name__ = tool_spec.name
    tool.__qualname__ = tool_spec.name
    tool.__doc__ = tool_spec.description
    tool.__signature__ = Signature(
        parameters=[
            Parameter(
                parameter.name,
                kind=Parameter.POSITIONAL_OR_KEYWORD,
                annotation=parameter.annotation,
                default=parameter.default,
            )
            for parameter in tool_spec.parameters
        ],
        return_annotation=str,
    )
    tool.__annotations__ = {
        parameter.name: parameter.annotation
        for parameter in tool_spec.parameters
    } | {"return": str}
    return factory(tool, name=tool_spec.name, description=tool_spec.description)


def _build_action(tool_spec: ActionToolSpec, *, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Action:
    if args and kwargs:
        raise TypeError(f"{tool_spec.name} accepts either positional or keyword arguments, not both.")
    if args:
        return tool_spec.build_action(*args)
    return tool_spec.build_action(**kwargs)


def _load_tool_factory() -> Callable[..., Any]:
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise RuntimeError(
            "langchain and langchain-openai are not installed. Install dependencies before using the LangChain agent."
        ) from exc

    def factory(fn: Callable[..., Any], *, name: str, description: str) -> Any:
        return StructuredTool.from_function(
            func=fn,
            name=name,
            description=description,
        )

    return factory
