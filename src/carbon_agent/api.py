"""FastAPI boundary for the V6 dual-runtime agent service."""

from typing import Any, Literal, Protocol
from uuid import uuid4

from .bootstrap import create_default_orchestrator
from .contracts import AgentRequest


class AgentRuntime(Protocol):
    def handle(self, request: AgentRequest): ...


def create_app(orchestrator: AgentRuntime | None = None):
    try:
        from fastapi import FastAPI
        from pydantic import BaseModel, Field
    except ImportError as error:
        raise RuntimeError(
            "启动 API 需要 fastapi 和 uvicorn，请安装 requirements.txt。"
        ) from error

    active_orchestrator = orchestrator or create_default_orchestrator()
    app = FastAPI(
        title="Carbon Credit Agent API",
        version="6.0.0",
        description="Evidence-grounded assistant; all risk outputs require human review.",
    )

    class ChatRequest(BaseModel):
        text: str = Field(min_length=1, max_length=8000)
        session_id: str | None = None
        actor_id: str = Field(default="api-user", min_length=1, max_length=128)
        intent: Literal[
            "auto", "chat", "knowledge", "registry", "risk_review"
        ] = "auto"
        payload: dict[str, Any] = Field(default_factory=dict)
        approval_granted: bool = False
        request_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "6.0.0"}

    @app.post("/v1/agent/chat")
    def chat(body: ChatRequest) -> dict[str, Any]:
        response = active_orchestrator.handle(
            AgentRequest(
                text=body.text,
                session_id=body.session_id,
                actor_id=body.actor_id,
                intent=body.intent,
                payload=body.payload,
                approval_granted=body.approval_granted,
                request_id=body.request_id,
            )
        )
        return response.to_dict()

    @app.get("/v1/executions/{request_id}/events")
    def execution_events(request_id: str) -> dict[str, Any]:
        getter = getattr(active_orchestrator, "get_events", None)
        if getter is None:
            return {"request_id": request_id, "events": []}
        return {"request_id": request_id, "events": getter(request_id)}

    @app.get("/v1/architecture")
    def architecture() -> dict[str, Any]:
        getter = getattr(active_orchestrator, "get_architecture", None)
        if getter is None:
            return {
                "runtime": "custom",
                "nodes": ["planner", "tool_executor", "output_verifier"],
                "edges": [],
            }
        return getter()

    return app


app = create_app()
