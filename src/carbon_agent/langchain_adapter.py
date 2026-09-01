"""LangChain adapters for the project's typed tools and DeepSeek planner."""

from __future__ import annotations

import os
from typing import Any, Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field, create_model

from .contracts import Message
from .planner import ToolDecision
from .tooling import ToolSpec


JSON_TYPES: dict[str, type[Any]] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def args_model_from_spec(spec: ToolSpec) -> type[BaseModel]:
    """Convert the existing JSON Schema contract to a LangChain Pydantic tool."""
    properties = spec.parameters.get("properties", {})
    required = set(spec.parameters.get("required", []))
    fields: dict[str, Any] = {}
    for name, definition in properties.items():
        python_type = JSON_TYPES.get(definition.get("type"), Any)
        description = definition.get("description", "")
        if name in required:
            fields[name] = (python_type, Field(..., description=description))
        else:
            fields[name] = (python_type | None, Field(None, description=description))
    return create_model(
        f"{spec.name.title().replace('_', '')}Input",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def langchain_tool_from_spec(
    spec: ToolSpec,
    handler: Callable[[dict[str, Any]], Any] | None = None,
):
    """Create a real StructuredTool while keeping business execution injectable."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as error:
        raise RuntimeError("V6 需要安装 langchain。") from error

    def invoke_tool(**kwargs: Any) -> Any:
        if handler is None:
            raise RuntimeError("该 LangChain Tool 仅用于模型 Schema 绑定。")
        return handler(kwargs)

    return StructuredTool.from_function(
        func=invoke_tool,
        name=spec.name,
        description=spec.description,
        args_schema=args_model_from_spec(spec),
    )


class LangChainDeepSeekPlanner:
    """Tool planner using LangChain's provider-specific DeepSeek integration."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        thinking_mode: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 900,
        model: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model_name = model_name or os.getenv(
            "DEEPSEEK_MODEL", "deepseek-v4-flash"
        )
        self.thinking_mode = thinking_mode or os.getenv(
            "DEEPSEEK_THINKING", "disabled"
        )
        if self.thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("DEEPSEEK_THINKING 仅支持 enabled 或 disabled。")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._provided_model = model

    def _model(self):
        if self._provided_model is not None:
            return self._provided_model
        if not self.api_key:
            raise RuntimeError("未检测到 DEEPSEEK_API_KEY，无法执行 V6 LangGraph。")
        try:
            from langchain_deepseek import ChatDeepSeek
        except ImportError as error:
            raise RuntimeError("V6 需要安装 langchain-deepseek。") from error
        return ChatDeepSeek(
            model=self.model_name,
            api_key=self.api_key,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            max_retries=2,
            extra_body={"thinking": {"type": self.thinking_mode}},
        )

    def decide(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> ToolDecision:
        try:
            from langchain_core.messages import (
                AIMessage,
                HumanMessage,
                SystemMessage,
            )
        except ImportError as error:
            raise RuntimeError("V6 需要安装 langchain-core。") from error

        converted = []
        for message in messages:
            if message.role == "assistant":
                converted.append(AIMessage(content=message.content))
            elif message.role == "user":
                converted.append(HumanMessage(content=message.content))
            else:
                converted.append(SystemMessage(content=message.content))

        model = self._model().bind_tools(
            [langchain_tool_from_spec(spec) for spec in tools]
        )
        response = model.invoke(converted)
        if response.tool_calls:
            selected = response.tool_calls[0]
            return ToolDecision.call(selected["name"], dict(selected.get("args", {})))

        content = response.content
        if isinstance(content, list):
            answer = "".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in content
            ).strip()
        else:
            answer = str(content or "").strip()
        if not answer:
            raise RuntimeError("LangChain 模型既未选择工具，也未返回最终回答。")
        return ToolDecision.finish(answer)
