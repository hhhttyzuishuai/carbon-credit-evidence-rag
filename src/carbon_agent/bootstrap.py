"""Dependency wiring for the local V5 production-like runtime."""

from __future__ import annotations

from pathlib import Path

from .audit import JsonlAuditLog
from .context import ArtifactStore, ContextWindowManager
from .execution_store import SQLiteExecutionStore
from .harness import AgentHarness
from .knowledge import ExistingRAGRetriever
from .memory import SQLiteConversationStore
from .planner import DeepSeekToolPlanner
from .tooling import build_default_tool_registry


def create_default_orchestrator(
    runtime_directory: str | Path = "runtime",
) -> AgentHarness:
    runtime_path = Path(runtime_directory)
    return AgentHarness(
        planner=DeepSeekToolPlanner(),
        tools=build_default_tool_registry(ExistingRAGRetriever()),
        execution_store=SQLiteExecutionStore(runtime_path / "executions.sqlite3"),
        conversation_store=SQLiteConversationStore(
            runtime_path / "agent_memory.sqlite3"
        ),
        context_manager=ContextWindowManager(),
        artifact_store=ArtifactStore(runtime_path / "artifacts"),
        audit_log=JsonlAuditLog(runtime_path / "audit.jsonl"),
    )
