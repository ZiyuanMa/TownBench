from __future__ import annotations

import json
import types
from inspect import Parameter
from typing import Any, Callable, get_args, get_origin

from engine.action_models import Action
from engine.actions import ActionSpec, ActionToolSpec, TOOL_ACTION_SPECS
from engine.rendering import render_tool_result
from runtime.env import TownBenchEnv

ToolFactory = Callable[..., Any]


def build_townbench_tools(
    env: TownBenchEnv,
    *,
    tool_factory: ToolFactory | None = None,
) -> list[Any]:
    factory = tool_factory or _load_tool_factory()
    return [_build_tool(spec, env, factory) for spec in TOOL_ACTION_SPECS]


def _build_tool(
    spec: ActionSpec,
    env: TownBenchEnv,
    factory: ToolFactory,
) -> Any:
    tool_spec = spec.tool
    if tool_spec is None:
        raise ValueError(f"Action `{spec.action_type}` is not exposed as an agent tool.")

    async def invoke_tool(_ctx: Any, args: str) -> str:
        parsed_args = _parse_tool_args(tool_spec.name, args)
        action = _build_action(tool_spec, kwargs=parsed_args)
        return render_tool_result(action, env.step(action))

    return factory(
        name=tool_spec.name,
        description=tool_spec.description,
        params_json_schema=_build_params_json_schema(tool_spec),
        on_invoke_tool=invoke_tool,
    )


def _parse_tool_args(tool_name: str, args: str) -> dict[str, Any]:
    if not args:
        return {}
    parsed = json.loads(args)
    if not isinstance(parsed, dict):
        raise TypeError(f"{tool_name} expects a JSON object of arguments.")
    return parsed


def _build_action(tool_spec: ActionToolSpec, *, kwargs: dict[str, Any]) -> Action:
    return tool_spec.build_action(**kwargs)


def _build_params_json_schema(tool_spec: ActionToolSpec) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in tool_spec.parameters:
        properties[parameter.name] = _parameter_json_schema(parameter.annotation)
        if parameter.default is Parameter.empty:
            required.append(parameter.name)
        else:
            properties[parameter.name]["default"] = parameter.default

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _parameter_json_schema(annotation: Any) -> dict[str, Any]:
    if _is_optional_object(annotation):
        return {"anyOf": [{"type": "object"}, {"type": "null"}]}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is dict or get_origin(annotation) is dict:
        return {"type": "object"}
    return {"type": "string"}


def _is_optional_object(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin not in {types.UnionType, getattr(types, "UnionType", object)}:
        return False
    args = set(get_args(annotation))
    return type(None) in args and any(item is dict or get_origin(item) is dict for item in args)


def _load_tool_factory() -> ToolFactory:
    try:
        from agents import FunctionTool
    except ImportError as exc:
        raise RuntimeError(
            "openai-agents is not installed. Install dependencies before using the OpenAI Agents baseline."
        ) from exc

    def factory(
        *,
        name: str,
        description: str,
        params_json_schema: dict[str, Any],
        on_invoke_tool: Callable[[Any, str], Any],
    ) -> Any:
        return FunctionTool(
            name=name,
            description=description,
            params_json_schema=params_json_schema,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=False,
        )

    return factory
