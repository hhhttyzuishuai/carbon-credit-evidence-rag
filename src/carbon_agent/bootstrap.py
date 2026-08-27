"""Dependency wiring for the local production-like runtime."""

from __future__ import annotations

from pathlib import Path

from .audit import JsonlAuditLog
from .business_tools import ExperimentalRiskTool, LocalRegistryTool
from .knowledge import ExistingRAGRetriever
from .llm import DeepSeekGateway
from .memory import SQLiteConversationStore
from .orchestrator import MultiAgentOrchestrator
from .routing import RouterAgent
from .specialists import OutputVerifierAgent, RegistryAgent, RiskReviewAgent
from .v2_conversation import ConversationalAgent
from .v3_knowledge_agent import KnowledgeAgent


def create_default_orchestrator(
    runtime_directory: str | Path = "runtime",
) -> MultiAgentOrchestrator:
    runtime_path = Path(runtime_directory)
    store = SQLiteConversationStore(runtime_path / "agent_memory.sqlite3")
    gateway = DeepSeekGateway()
    return MultiAgentOrchestrator(
        router=RouterAgent(),
        conversation_agent=ConversationalAgent(gateway, store),
        knowledge_agent=KnowledgeAgent(
            gateway, ExistingRAGRetriever(), store
        ),
        registry_agent=RegistryAgent(LocalRegistryTool(), store),
        risk_review_agent=RiskReviewAgent(ExperimentalRiskTool(), store),
        verifier=OutputVerifierAgent(),
        audit_log=JsonlAuditLog(runtime_path / "audit.jsonl"),
    )

