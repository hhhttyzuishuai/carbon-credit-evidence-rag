import json
import tempfile
import unittest
from pathlib import Path

from carbon_agent.audit import JsonlAuditLog, redact
from carbon_agent.contracts import AgentRequest
from carbon_agent.knowledge import Evidence
from carbon_agent.llm import FakeGateway
from carbon_agent.memory import SQLiteConversationStore
from carbon_agent.orchestrator import MultiAgentOrchestrator
from carbon_agent.routing import RouterAgent
from carbon_agent.specialists import (
    OutputVerifierAgent,
    RegistryAgent,
    RiskReviewAgent,
)
from carbon_agent.v2_conversation import ConversationalAgent
from carbon_agent.v3_knowledge_agent import KnowledgeAgent


class StubRegistryTool:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def lookup(self, project_id: str):
        self.calls.append(project_id)
        if project_id != "ACR102":
            return None
        return {
            "project_id": "ACR102",
            "project_name": "Air Bag Gas Substitution",
            "voluntary_status": "Completed",
            "registry": "ACR",
            "total_credits_issued": 100,
            "total_credits_retired": 20,
            "total_credits_remaining": 80,
            "source_workbook": "registry.xlsx",
            "source_sheet": "PROJECTS",
            "source_excel_row": 5,
        }


class StubRiskTool:
    def __init__(self) -> None:
        self.calls = 0

    def review(self, payload):
        self.calls += 1
        return {
            "feature_payload": {},
            "review_result": {
                "decision": "review_required",
                "reason": "仅提供实验性信号。",
                "registry_source": None,
            },
        }


class StubRetriever:
    def retrieve(self, query: str, top_k: int = 5):
        return [
            Evidence(
                evidence_id="S1",
                text="规则证据",
                source_file="rule.pdf",
                page_number=1,
                document_type="official_rule",
                language="zh",
            )
        ]


class MultiAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        store = SQLiteConversationStore(root / "memory.sqlite3")
        self.registry_tool = StubRegistryTool()
        self.risk_tool = StubRiskTool()
        self.gateway = FakeGateway(["通用回答", "规则要求如下。[S1]"])
        self.audit_path = root / "audit.jsonl"
        self.orchestrator = MultiAgentOrchestrator(
            router=RouterAgent(),
            conversation_agent=ConversationalAgent(self.gateway, store),
            knowledge_agent=KnowledgeAgent(self.gateway, StubRetriever(), store),
            registry_agent=RegistryAgent(self.registry_tool, store),
            risk_review_agent=RiskReviewAgent(self.risk_tool, store),
            verifier=OutputVerifierAgent(),
            audit_log=JsonlAuditLog(self.audit_path),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_router_selects_four_specialist_routes(self) -> None:
        router = RouterAgent()
        self.assertEqual(router.route(AgentRequest("你好")), "chat")
        self.assertEqual(router.route(AgentRequest("管理办法有何规定？")), "knowledge")
        self.assertEqual(router.route(AgentRequest("查询 ACR102 的登记状态")), "registry")
        self.assertEqual(router.route(AgentRequest("进行风险评分")), "risk_review")

    def test_registry_route_calls_exact_lookup_and_returns_provenance(self) -> None:
        response = self.orchestrator.handle(
            AgentRequest("查询 ACR102 的登记状态")
        )
        self.assertEqual(response.agent, "registry_agent")
        self.assertEqual(self.registry_tool.calls, ["ACR102"])
        self.assertEqual(response.sources[0].locator, "sheet:PROJECTS;excel_row:5")
        self.assertTrue(response.metadata["verification"]["passed"])

    def test_risk_tool_requires_explicit_approval(self) -> None:
        denied = self.orchestrator.handle(
            AgentRequest("进行风险评分", intent="risk_review")
        )
        self.assertEqual(denied.metadata["status"], "approval_required")
        self.assertEqual(self.risk_tool.calls, 0)

        allowed = self.orchestrator.handle(
            AgentRequest(
                "进行风险评分",
                intent="risk_review",
                payload={"project_id": "ACR102"},
                approval_granted=True,
            )
        )
        self.assertEqual(allowed.metadata["status"], "success")
        self.assertEqual(self.risk_tool.calls, 1)

    def test_audit_log_records_trace_and_redacts_secrets(self) -> None:
        self.orchestrator.handle(
            AgentRequest(
                "查询 ACR102 的登记状态",
                payload={"project_id": "ACR102", "api_key": "never-log-me"},
            )
        )
        event = json.loads(self.audit_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(event["payload"]["api_key"], "***REDACTED***")
        self.assertTrue(event["trace_id"])
        self.assertNotIn("never-log-me", self.audit_path.read_text(encoding="utf-8"))

    def test_specialist_failure_is_isolated(self) -> None:
        class FailingRegistry:
            def lookup(self, project_id: str):
                raise OSError("database unavailable")

        self.orchestrator.registry_agent = RegistryAgent(FailingRegistry())
        response = self.orchestrator.handle(
            AgentRequest("查询 ACR102 的登记状态")
        )
        self.assertEqual(response.agent, "orchestrator")
        self.assertEqual(response.metadata["error_type"], "OSError")
        self.assertNotIn("database unavailable", response.answer)

    def test_redaction_is_recursive(self) -> None:
        self.assertEqual(
            redact({"nested": [{"access_token": "secret"}]}),
            {"nested": [{"access_token": "***REDACTED***"}]},
        )


if __name__ == "__main__":
    unittest.main()
