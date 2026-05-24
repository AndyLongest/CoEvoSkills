from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from utils.llm.types import Message, Response


class LLMClient(ABC):
    """Abstract LLM client interface.

    Concrete implementations: AnthropicClient, OpenAIClient, DeepSeekClient.
    Supports text generation with optional tool use (function calling).
    """

    def __init__(self, model: str, api_key: str | None = None):
        self.model = model
        self.api_key = api_key

    @abstractmethod
    def send(
        self,
        messages: list[Message | dict],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Response:
        """Send messages to the LLM and return a structured response.

        Args:
            messages: Conversation history. Accepts Message objects or dicts
                with keys like {'role': 'user', 'content': '...'}.
            system: System prompt (handled per-provider convention).
            tools: Optional list of tool/function definitions for tool use.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens in the response.

        Returns:
            Response with message content and optional tool calls.
        """
        ...

    @staticmethod
    def _normalize_messages(messages: list[Message | dict]) -> list[Message]:
        """Convert mixed message formats to a list of Message objects."""
        result: list[Message] = []
        for msg in messages:
            if isinstance(msg, Message):
                result.append(msg)
            elif isinstance(msg, dict):
                result.append(Message(
                    role=msg.get("role", "user"),
                    content=msg.get("content"),
                    name=msg.get("name"),
                ))
            else:
                result.append(Message(role="user", content=str(msg)))
        return result
