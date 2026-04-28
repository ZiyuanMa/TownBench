from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import (
    _convert_from_v1_to_chat_completions,
    _convert_message_to_dict,
)


REASONING_CONTENT_FIELD = "reasoning_content"


class DeepSeekChatOpenAI(ChatOpenAI):
    """ChatOpenAI variant that preserves DeepSeek thinking-mode metadata."""

    def _get_request_payload(self, input_, *, stop=None, **kwargs: Any) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "messages" not in payload:
            return payload

        messages = self._convert_input(input_).to_messages()
        payload["messages"] = [
            _convert_message_with_reasoning_content(message)
            for message in messages
        ]
        return payload

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info=generation_info)
        response_dict = response if isinstance(response, dict) else response.model_dump()
        choices = response_dict.get("choices") or []
        for generation, choice in zip(result.generations, choices):
            message = getattr(generation, "message", None)
            raw_message = choice.get("message", {}) if isinstance(choice, dict) else {}
            reasoning_content = raw_message.get(REASONING_CONTENT_FIELD)
            if isinstance(message, AIMessage) and isinstance(reasoning_content, str):
                message.additional_kwargs[REASONING_CONTENT_FIELD] = reasoning_content
        return result


def _convert_message_with_reasoning_content(message) -> dict:
    converted = (
        _convert_message_to_dict(_convert_from_v1_to_chat_completions(message))
        if isinstance(message, AIMessage)
        else _convert_message_to_dict(message)
    )
    if isinstance(message, AIMessage):
        reasoning_content = message.additional_kwargs.get(REASONING_CONTENT_FIELD)
        if isinstance(reasoning_content, str):
            converted[REASONING_CONTENT_FIELD] = reasoning_content
    return converted
