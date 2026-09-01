"""Dependency wiring for both the V5 custom and V6 LangGraph runtimes."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .audit import JsonlAuditLog
from .context import ArtifactStore, ContextWindowManager
from .execution_store import SQLiteExecutionStore
from .harness import AgentHarness
from .knowledge import ExistingRAGRetriever
from .langchain_adapter import LangChainDeepSeekPlanner
from .langgraph_runtime import LangGraphAgentRuntime
from .memory import SQLiteConversationStore
from .planner import DeepSeekToolPlanner
from .tooling import build_default_tool_registry


def _load_project_environment() -> None:
    """Load local configuration for CLI, API, and Streamlit entry points."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def create_custom_runtime(
    runtime_directory: str | Path = "runtime",
) -> AgentHarness:
    _load_project_environment()
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


def create_langgraph_runtime(
    runtime_directory: str | Path = "runtime",
) -> LangGraphAgentRuntime:
    _load_project_environment()
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError as error:
        raise RuntimeError(
            "V6 需要安装 langgraph-checkpoint-sqlite。"
        ) from error

    runtime_path = Path(runtime_directory)
    runtime_path.mkdir(parents=True, exist_ok=True)
    checkpoint_connection = sqlite3.connect(
        runtime_path / "langgraph_checkpoints.sqlite3",
        check_same_thread=False,
    )
    checkpoint_connection.execute("PRAGMA journal_mode = WAL")
    runtime = LangGraphAgentRuntime(
        planner=LangChainDeepSeekPlanner(),
        tools=build_default_tool_registry(ExistingRAGRetriever()),
        execution_store=SQLiteExecutionStore(
            runtime_path / "langgraph_executions.sqlite3"
        ),
        conversation_store=SQLiteConversationStore(
            runtime_path / "langgraph_memory.sqlite3"
        ),
        context_manager=ContextWindowManager(),
        artifact_store=ArtifactStore(runtime_path / "langgraph_artifacts"),
        checkpointer=SqliteSaver(checkpoint_connection),
        audit_log=JsonlAuditLog(runtime_path / "langgraph_audit.jsonl"),
    )
    # Keep the SQLite connection alive for the compiled graph's lifetime.
    runtime._checkpoint_connection = checkpoint_connection
    return runtime


def create_default_orchestrator(
    runtime_directory: str | Path = "runtime",
    runtime_kind: str | None = None,
):
    selected = (runtime_kind or os.getenv("AGENT_RUNTIME", "langgraph")).lower()
    if selected == "custom":
        return create_custom_runtime(runtime_directory)
    if selected == "langgraph":
        return create_langgraph_runtime(runtime_directory)
    raise ValueError("AGENT_RUNTIME 仅支持 custom 或 langgraph。")
