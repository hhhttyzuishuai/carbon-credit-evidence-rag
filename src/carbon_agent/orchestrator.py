"""V4 multi-agent orchestration, tracing, and failure isolation."""

from __future__ import annotations

import time
from typing import Protocol

from .audit import JsonlAuditLog
from .contracts import AgentRequest, AgentResponse
from .routing import RouterAgent
from .specialists import OutputVerifierAgent, RegistryAgent, RiskReviewAgent
from .v2_conversation import ConversationalAgent
from .v3_knowledge_agent import KnowledgeAgent


class RequestSpecialist(Protocol):
    def answer(self, request: AgentRequest) -> AgentResponse: ...


class MultiAgentOrchestrator:
    def __init__(
        self,
        router: RouterAgent,
        conversation_agent: ConversationalAgent,
        knowledge_agent: KnowledgeAgent,
        registry_agent: RegistryAgent,
        risk_review_agent: RiskReviewAgent,
        verifier: OutputVerifierAgent,
        audit_log: JsonlAuditLog,
    ) -> None:
        self.router = router
        self.conversation_agent = conversation_agent
        self.knowledge_agent = knowledge_agent
        self.registry_agent = registry_agent
        self.risk_review_agent = risk_review_agent
        self.verifier = verifier
        self.audit_log = audit_log

    def handle(self, request: AgentRequest) -> AgentResponse:
        started = time.perf_counter()
        route = self.router.route(request)
        try:
            if route == "chat":
                response = self.conversation_agent.answer(
                    request.text, session_id=request.session_id
                )
            elif route == "knowledge":
                response = self.knowledge_agent.answer(
                    request.text, session_id=request.session_id
                )
            elif route == "registry":
                response = self.registry_agent.answer(request)
            elif route == "risk_review":
                response = self.risk_review_agent.answer(request)
            else:
                raise ValueError(f"不支持的路由：{route}")

            response.metadata["route"] = route
            response.metadata["request_id"] = request.request_id
            response.metadata["latency_ms"] = round(
                (time.perf_counter() - started) * 1000, 3
            )
            response = self.verifier.verify(route, response)
            self._audit(request, response, status="success")
            return response
        except Exception as error:
            failure = AgentResponse(
                answer="系统暂时无法完成本次请求，需要人工复核。",
                agent="orchestrator",
                session_id=request.session_id,
                metadata={
                    "route": route,
                    "request_id": request.request_id,
                    "error_type": type(error).__name__,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                },
            )
            self._audit(request, failure, status="failed")
            return failure

    def _audit(
        self,
        request: AgentRequest,
        response: AgentResponse,
        status: str,
    ) -> None:
        self.audit_log.write(
            {
                "event": "agent_request_completed",
                "status": status,
                "request_id": request.request_id,
                "trace_id": response.trace_id,
                "actor_id": request.actor_id,
                "session_id": response.session_id,
                "requested_intent": request.intent,
                "route": response.metadata.get("route"),
                "approval_granted": request.approval_granted,
                "payload": request.payload,
                "response_agent": response.agent,
                "tool_calls": response.tool_calls,
                "source_count": len(response.sources),
                "latency_ms": response.metadata.get("latency_ms"),
                "error_type": response.metadata.get("error_type"),
            }
        )
