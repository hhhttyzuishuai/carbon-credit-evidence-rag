import unittest

from fastapi.testclient import TestClient

from carbon_agent.api import create_app
from carbon_agent.contracts import AgentResponse


class StubOrchestrator:
    def __init__(self) -> None:
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return AgentResponse(
            answer="API route ok",
            agent="registry_agent",
            session_id=request.session_id,
            metadata={"route": request.intent},
        )


class AgentApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = StubOrchestrator()
        self.client = TestClient(create_app(self.orchestrator))

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "version": "6.0.0"})

    def test_architecture_endpoint_has_safe_fallback(self) -> None:
        response = self.client.get("/v1/architecture")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["runtime"], "custom")
        self.assertIn("planner", response.json()["nodes"])

    def test_chat_endpoint_preserves_structured_request(self) -> None:
        response = self.client.post(
            "/v1/agent/chat",
            json={
                "text": "查询 ACR102",
                "session_id": "session-1",
                "actor_id": "reviewer-7",
                "intent": "registry",
                "payload": {"project_id": "ACR102"},
                "approval_granted": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "API route ok")
        request = self.orchestrator.requests[0]
        self.assertEqual(request.actor_id, "reviewer-7")
        self.assertEqual(request.payload["project_id"], "ACR102")

    def test_chat_endpoint_validates_empty_text(self) -> None:
        response = self.client.post("/v1/agent/chat", json={"text": ""})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
