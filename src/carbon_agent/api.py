"""FastAPI boundary for the V4 multi-agent service."""

from typing import Any, Literal

from .bootstrap import create_default_orchestrator
from .contracts import AgentRequest
from .orchestrator import MultiAgentOrchestrator


def create_app(orchestrator: MultiAgentOrchestrator | None = None):
    try:
        from fastapi import FastAPI
        from pydantic import BaseModel, Field
    except ImportError as error:
        raise RuntimeError(
            "启动 API 需要 fastapi 和 uvicorn，请安装 requirements.txt。"
        ) from error

    active_orchestrator = orchestrator or create_default_orchestrator()
    app = FastAPI(
        title="Carbon Credit Multi-Agent API",
        version="4.0.0",
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "4.0.0"}

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
            )
        )
        return response.to_dict()

    return app


app = create_app()
