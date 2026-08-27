"""LLM gateway: agents depend on this protocol, not a vendor SDK."""

from __future__ import annotations

import os
from typing import Protocol, Sequence

from .contracts import Message


class ChatGateway(Protocol):
    def complete(self, messages: Sequence[Message]) -> str:
        """Return one assistant message for the supplied conversation."""


class DeepSeekGateway:
    """OpenAI-compatible DeepSeek gateway with environment-only secrets."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.base_url = base_url or os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete(self, messages: Sequence[Message]) -> str:
        if not self.api_key:
            raise RuntimeError(
                "未检测到 DEEPSEEK_API_KEY。请复制 .env.example 为 .env 并填写密钥。"
            )

        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("缺少 openai 依赖，请安装 requirements.txt。") from error

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[message.to_llm_dict() for message in messages],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content or ""


class FakeGateway:
    """Deterministic test double used by offline tests and demos."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or ["测试回答"])
        self.calls: list[list[Message]] = []

    def complete(self, messages: Sequence[Message]) -> str:
        self.calls.append(list(messages))
        if not self.responses:
            raise RuntimeError("FakeGateway 没有剩余响应。")
        return self.responses.pop(0)

