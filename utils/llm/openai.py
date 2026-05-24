from __future__ import annotations

import json
import os
from typing import Any

from utils.llm.client import LLMClient
from utils.llm.types import Message, Response, ToolCall, Usage


class OpenAIClient(LLMClient):
    """LLM client for OpenAI GPT models via the Chat Completions API."""

    def __init__(self, model: str = "gpt-5", api_key: str | None = None):
        super().__init__(model=model, api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def send(
        self,
        messages: list[Message | dict],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Response:
        import openai

        client = openai.OpenAI(api_key=self.api_key)
        normalized = self._normalize_messages(messages)

        openai_messages = self._to_openai_messages(normalized, system)

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)

        return self._from_openai_response(resp)

    def _to_openai_messages(self, messages: list[Message], system: str | None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if system:
            result.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                result.append({"role": "system", "content": msg.content or ""})
                continue

            entry: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                entry["content"] = msg.content
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_results:
                for i, tr in enumerate(msg.tool_results):
                    tc = msg.tool_calls[i] if msg.tool_calls and i < len(msg.tool_calls) else None
                    result.append({
                        "role": "tool",
                        "tool_call_id": tr.tool_call_id,
                        "name": tc.name if tc else tr.name,
                        "content": tr.content,
                    })
                continue
            result.append(entry)
        return result

    def _to_openai_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", t.get("input_schema", {})),
                },
            })
        return result

    def _from_openai_response(self, resp: Any) -> Response:
        choice = resp.choices[0] if resp.choices else None
        if choice is None:
            return Response(message=Message.assistant(content=""))

        msg = choice.message
        text = msg.content or ""
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args = {}
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    pass
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = Usage(
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )

        return Response(
            message=Message.assistant(
                content=text if text else "",
                tool_calls=tool_calls if tool_calls else None,
            ),
            usage=usage,
            stop_reason=choice.finish_reason or "",
        )
