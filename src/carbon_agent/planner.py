"""Model-driven planning contract for the V5 agent loop."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from .contracts import Message
from .tooling import ToolSpec


@dataclass(frozen=True)
class ToolDecision:
    action: str
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    answer: str | None = None

    @classmethod
    def call(cls, tool_name: str, arguments: dict[str, Any]) -> "ToolDecision":
        return cls(action="tool", tool_name=tool_name, arguments=arguments)

    @classmethod
    def finish(cls, answer: str) -> "ToolDecision":
        return cls(action="final", answer=answer)


class ToolPlanner(Protocol):
    def decide(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> ToolDecision:
        """Choose one tool call or produce the final answer."""


class DeepSeekToolPlanner:
    """OpenAI-compatible tool-calling planner used by the V5 runtime."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        thinking_mode: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 900,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.base_url = base_url or os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.thinking_mode = thinking_mode or os.getenv(
            "DEEPSEEK_THINKING", "disabled"
        )
        if self.thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("DEEPSEEK_THINKING 仅支持 enabled 或 disabled。")
        self.temperature = temperature
        self.max_tokens = max_tokens

    def decide(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> ToolDecision:
        if not self.api_key:
            raise RuntimeError("未检测到 DEEPSEEK_API_KEY，无法执行 V5 Agent Loop。")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("缺少 openai 依赖，请安装 requirements.txt。") from error

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[message.to_llm_dict() for message in messages],
            tools=[tool.as_model_tool() for tool in tools],
            tool_choice="auto",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            extra_body={"thinking": {"type": self.thinking_mode}},
        )
        message = response.choices[0].message
        if message.tool_calls:
            call = message.tool_calls[0]
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as error:
                raise ValueError("模型返回了无效的工具参数 JSON。") from error
            return ToolDecision.call(call.function.name, arguments)

        answer = (message.content or "").strip()
        if not answer:
            raise RuntimeError("模型既未选择工具，也未返回最终回答。")
        return ToolDecision.finish(answer)


class FakeToolPlanner:
    """Scripted planner for deterministic loop, recovery, and eval tests."""

    def __init__(self, decisions: list[ToolDecision]) -> None:
        self.decisions = list(decisions)
        self.calls: list[dict[str, Any]] = []

    def decide(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> ToolDecision:
        self.calls.append(
            {
                "messages": list(messages),
                "tool_names": [tool.name for tool in tools],
            }
        )
        if not self.decisions:
            raise RuntimeError("FakeToolPlanner 没有剩余决策。")
        return self.decisions.pop(0)
