from __future__ import annotations

from typing import Any

from agents.models.default_models import get_default_model
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_provider import OpenAIProvider


class DeepSeekOpenAIProvider(OpenAIProvider):
    """OpenAI-compatible provider tuned for DeepSeek thinking-mode chat completions."""

    def get_model(self, model_name: str | None) -> Model:
        resolved_model_name = model_name if model_name is not None else get_default_model()
        return DeepSeekChatCompletionsModel(
            model=resolved_model_name,
            openai_client=self._get_client(),
        )


class DeepSeekChatCompletionsModel(OpenAIChatCompletionsModel):
    async def _fetch_response(
        self,
        system_instructions: str | None,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        span,
        tracing,
        stream: bool = False,
        prompt=None,
    ):
        return await super()._fetch_response(
            system_instructions,
            _prepare_deepseek_input_items(input),
            model_settings,
            tools,
            output_schema,
            handoffs,
            span,
            tracing,
            stream=stream,
            prompt=prompt,
        )


def _prepare_deepseek_input_items(items: str | list[Any]) -> str | list[Any]:
    if isinstance(items, str):
        return items

    prepared: list[Any] = []
    index = 0
    while index < len(items):
        item = items[index]
        if (
            _is_reasoning_item(item)
            and index + 2 < len(items)
            and _is_assistant_output_message(items[index + 1])
            and _is_function_call(items[index + 2])
        ):
            prepared.append(items[index + 1])
            prepared.append(_without_reasoning_id(item))
            index += 2
            continue
        if _is_reasoning_item(item):
            prepared.append(_without_reasoning_id(item))
        else:
            prepared.append(item)
        index += 1
    return prepared


def _is_reasoning_item(item: Any) -> bool:
    return _item_type(item) == "reasoning"


def _is_assistant_output_message(item: Any) -> bool:
    return (
        _item_type(item) == "message"
        and _item_value(item, "role") == "assistant"
        and bool(_item_value(item, "content"))
    )


def _is_function_call(item: Any) -> bool:
    return _item_type(item) == "function_call"


def _item_type(item: Any) -> str | None:
    value = _item_value(item, "type")
    return value if isinstance(value, str) else None


def _item_value(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _without_reasoning_id(item: Any) -> Any:
    if isinstance(item, dict):
        if "id" not in item:
            return item
        stripped = dict(item)
        stripped.pop("id", None)
        return stripped
    if hasattr(item, "model_dump"):
        dumped = item.model_dump(exclude_unset=True)
        if isinstance(dumped, dict):
            dumped.pop("id", None)
            return dumped
    return item
