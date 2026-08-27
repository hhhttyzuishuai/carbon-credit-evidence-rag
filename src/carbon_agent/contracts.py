"""Stable contracts shared by every agent version."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


Role = Literal["system", "user", "assistant", "tool"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    name: str | None = None
    created_at: str = field(default_factory=utc_now)

    def to_llm_dict(self) -> dict[str, str]:
        payload = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass(frozen=True)
class Source:
    source_id: str
    label: str
    locator: str | None = None
    preview: str | None = None


@dataclass
class AgentResponse:
    answer: str
    agent: str
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    session_id: str | None = None
    sources: list[Source] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

