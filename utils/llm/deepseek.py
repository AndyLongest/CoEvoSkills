from __future__ import annotations

import os

from utils.llm.openai import OpenAIClient


class DeepSeekClient(OpenAIClient):
    """LLM client for DeepSeek models via OpenAI-compatible API.

    DeepSeek's API is fully compatible with the OpenAI protocol.
    Base URL: https://api.deepseek.com/v1
    Models: deepseek-chat (V3), deepseek-reasoner (R1)
    """

    BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None):
        super().__init__(model=model, api_key=api_key or os.getenv("DEEPSEEK_API_KEY"))

    def send(self, messages, system=None, tools=None, temperature=0.0, max_tokens=4096):
        import openai

        client = openai.OpenAI(api_key=self.api_key, base_url=self.BASE_URL)

        openai_messages = self._to_openai_messages(messages, system)

        kwargs = dict(
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
