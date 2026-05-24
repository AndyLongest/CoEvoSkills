from __future__ import annotations

import os
from typing import Any

from utils.llm.client import LLMClient
from utils.llm.types import Message, Response, ToolCall, Usage


class AnthropicClient(LLMClient):
    """LLM client for Anthropic Claude models via the Messages API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None):
        super().__init__(model=model, api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def send(
        self,
        messages: list[Message | dict],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Response:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        normalized = self._normalize_messages(messages)
        anthropic_messages = self._to_anthropic_messages(normalized)
        anthropic_tools = self._to_anthropic_tools(tools)

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=anthropic_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        resp = client.messages.create(**kwargs)

        return self._from_anthropic_response(resp)

    def _to_anthropic_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                continue
            entry: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                entry["content"] = msg.content
            if msg.tool_calls:
                tool_blocks = []
                for tc in msg.tool_calls:
                    tool_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                if tool_blocks:
                    entry["content"] = tool_blocks
            if msg.tool_results:
                tool_blocks = []
                for tr in msg.tool_results:
                    tool_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tr.tool_call_id,
                        "content": tr.content,
                    })
                entry["content"] = tool_blocks
            result.append(entry)
        return result

    def _to_anthropic_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        result: list[dict[str, Any]] = []
        for t in tools:
            entry: dict[str, Any] = {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", t.get("input_schema", {})),
            }
            result.append(entry)
        return result

    def _from_anthropic_response(self, resp: Any) -> Response:
        content_blocks = resp.content if hasattr(resp, "content") else []
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in content_blocks:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_calls.append(ToolCall(
                    id=getattr(block, "id", ""),
                    name=getattr(block, "name", ""),
                    arguments=dict(getattr(block, "input", {})),
                ))

        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0) if hasattr(resp, "usage") else 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) if hasattr(resp, "usage") else 0,
        )

        return Response(
            message=Message.assistant(
                content="\n".join(text_parts) if text_parts else "",
                tool_calls=tool_calls if tool_calls else None,
            ),
            usage=usage,
            stop_reason=getattr(resp, "stop_reason", ""),
        )
