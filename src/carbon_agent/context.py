"""Bounded prompt context and externalized large tool observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .contracts import Message


@dataclass(frozen=True)
class ContextResult:
    messages: list[Message]
    original_characters: int
    final_characters: int
    compacted_messages: int


class ContextWindowManager:
    def __init__(self, max_characters: int = 12000, recent_messages: int = 6) -> None:
        if max_characters < 500:
            raise ValueError("max_characters 至少为 500。")
        if recent_messages < 2:
            raise ValueError("recent_messages 至少为 2。")
        self.max_characters = max_characters
        self.recent_messages = recent_messages

    def compact(self, messages: Sequence[Message]) -> ContextResult:
        original = sum(len(message.content) for message in messages)
        if original <= self.max_characters:
            return ContextResult(list(messages), original, original, 0)

        system_messages = [message for message in messages if message.role == "system"]
        non_system = [message for message in messages if message.role != "system"]
        recent = non_system[-self.recent_messages :]
        older = non_system[: -self.recent_messages]
        summary_lines = [
            f"{message.role}: {message.content[:240]}"
            for message in older
        ]
        summary = Message(
            role="system",
            name="context_compactor",
            content=(
                "以下是较早上下文的确定性压缩摘要，仅用于理解对话，不作为业务证据：\n"
                + "\n".join(summary_lines)
            )[: max(500, self.max_characters // 3)],
        )
        compacted = [*system_messages[:1], summary, *recent]

        while sum(len(message.content) for message in compacted) > self.max_characters:
            if len(compacted) <= 3:
                break
            compacted.pop(2)

        current = sum(len(message.content) for message in compacted)
        if current > self.max_characters:
            budget_per_message = max(120, self.max_characters // len(compacted))
            compacted = [
                Message(
                    role=message.role,
                    name=message.name,
                    created_at=message.created_at,
                    content=message.content[:budget_per_message],
                )
                for message in compacted
            ]

        current = sum(len(message.content) for message in compacted)
        if current > self.max_characters:
            overflow = current - self.max_characters
            last = compacted[-1]
            compacted[-1] = Message(
                role=last.role,
                name=last.name,
                created_at=last.created_at,
                content=last.content[: max(0, len(last.content) - overflow)],
            )

        final = sum(len(message.content) for message in compacted)
        return ContextResult(compacted, original, final, len(older))


@dataclass(frozen=True)
class ExternalizedObservation:
    model_text: str
    artifact: dict[str, Any] | None


class ArtifactStore:
    def __init__(self, root: str | Path, threshold_characters: int = 5000) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.threshold_characters = threshold_characters

    def externalize(
        self,
        request_id: str,
        step: int,
        content: dict[str, Any],
    ) -> ExternalizedObservation:
        encoded = json.dumps(content, ensure_ascii=False, sort_keys=True)
        if len(encoded) <= self.threshold_characters:
            return ExternalizedObservation(encoded, None)

        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        request_directory = self.root / request_id
        request_directory.mkdir(parents=True, exist_ok=True)
        path = request_directory / f"step-{step}-{digest[:12]}.json"
        path.write_text(encoded, encoding="utf-8")
        preview = encoded[:1200]
        artifact = {
            "path": str(path),
            "sha256": digest,
            "characters": len(encoded),
        }
        model_text = json.dumps(
            {
                "externalized": True,
                "artifact": artifact,
                "preview": preview,
                "instruction": "需要更多细节时应请求更精确的工具查询。",
            },
            ensure_ascii=False,
        )
        return ExternalizedObservation(model_text, artifact)
