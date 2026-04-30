from __future__ import annotations

import json
from typing import Any


def extract_openai_messages(result: Any, *, model: str | None) -> list[dict[str, Any]]:
    raw_responses = getattr(result, "raw_responses", None)
    return _extract_openai_messages_from_raw_responses(raw_responses, model=model)


def extract_openai_messages_from_exception(
    exc: Exception,
    *,
    model: str | None,
) -> list[dict[str, Any]]:
    run_data = getattr(exc, "run_data", None)
    if run_data is None:
        return []
    raw_responses = getattr(run_data, "raw_responses", None)
    return _extract_openai_messages_from_raw_responses(raw_responses, model=model)


def extract_langchain_messages(result: Any) -> list[dict[str, Any]]:
    source_messages = _get_value(result, "messages")
    return _serialize_langchain_assistant_messages(source_messages)


def append_langchain_messages(
    collected_messages: list[dict[str, Any]],
    source_messages: Any,
) -> None:
    for message in _serialize_langchain_assistant_messages(source_messages):
        if not collected_messages or collected_messages[-1] != message:
            collected_messages.append(message)


def _extract_openai_messages_from_raw_responses(
    raw_responses: Any,
    *,
    model: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(raw_responses, list):
        return []

    try:
        from agents.models.chatcmpl_converter import Converter
    except ImportError:
        return []

    messages: list[dict[str, Any]] = []
    for response in raw_responses:
        to_input_items = getattr(response, "to_input_items", None)
        if not callable(to_input_items):
            continue
        try:
            converted = Converter.items_to_messages(to_input_items(), model=model)
        except Exception:
            continue
        for message in converted:
            if isinstance(message, dict) and message.get("role") == "assistant":
                messages.append(_to_plain_json(message))
    return messages


def _serialize_langchain_assistant_messages(source_messages: Any) -> list[dict[str, Any]]:
    if not isinstance(source_messages, list):
        return []

    messages: list[dict[str, Any]] = []
    for message in source_messages:
        serialized = _serialize_langchain_message(message)
        if serialized is not None:
            messages.append(serialized)
    return messages


def _serialize_langchain_message(message: Any) -> dict[str, Any] | None:
    role = _resolve_langchain_role(message)
    if role != "assistant":
        return None

    serialized: dict[str, Any] = {
        "role": "assistant",
        "content": _serialize_message_content(_get_value(message, "content")),
    }

    reasoning_content = _extract_reasoning_content(message)
    if isinstance(reasoning_content, str) and reasoning_content:
        serialized["reasoning_content"] = reasoning_content

    tool_calls = _get_value(message, "tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        serialized["tool_calls"] = [_serialize_tool_call(tool_call) for tool_call in tool_calls]

    return _to_plain_json(serialized)


def _resolve_langchain_role(message: Any) -> str | None:
    if isinstance(message, dict):
        role = message.get("role")
        if isinstance(role, str):
            return role
        message_type = message.get("type")
        return _role_from_type(message_type if isinstance(message_type, str) else None)

    role = _get_value(message, "role")
    if isinstance(role, str):
        return role

    message_type = _get_value(message, "type")
    if isinstance(message_type, str):
        return _role_from_type(message_type)

    class_name = message.__class__.__name__.lower()
    if "ai" in class_name:
        return "assistant"
    if "human" in class_name:
        return "user"
    if "tool" in class_name:
        return "tool"
    if "system" in class_name:
        return "system"
    return None


def _role_from_type(message_type: str | None) -> str | None:
    if message_type == "ai":
        return "assistant"
    if message_type == "human":
        return "user"
    if message_type == "tool":
        return "tool"
    if message_type == "system":
        return "system"
    return message_type


def _extract_reasoning_content(message: Any) -> str | None:
    additional_kwargs = _get_value(message, "additional_kwargs")
    if isinstance(additional_kwargs, dict):
        reasoning_content = additional_kwargs.get("reasoning_content")
        if isinstance(reasoning_content, str):
            return reasoning_content

    reasoning_content = _get_value(message, "reasoning_content")
    if isinstance(reasoning_content, str):
        return reasoning_content
    return None


def _serialize_message_content(content: Any) -> Any:
    if content is None:
        return ""
    return _to_plain_json(content)


def _serialize_tool_call(tool_call: Any) -> dict[str, Any]:
    tool_call_id = _get_value(tool_call, "id")

    function = _get_value(tool_call, "function")
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments")
    else:
        name = _get_value(tool_call, "name")
        arguments = _get_value(tool_call, "args")

    serialized: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": name or "",
            "arguments": _serialize_tool_call_arguments(arguments),
        },
    }
    if isinstance(tool_call_id, str) and tool_call_id:
        serialized["id"] = tool_call_id
    return serialized


def _serialize_tool_call_arguments(arguments: Any) -> str:
    if arguments is None:
        return "{}"
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(_to_plain_json(arguments), ensure_ascii=True, sort_keys=True)
    except TypeError:
        return str(arguments)


def _to_plain_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _to_plain_json(value.model_dump())
    if isinstance(value, dict):
        return {key: _to_plain_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_json(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain_json(item) for item in value]
    return value


def _get_value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)
