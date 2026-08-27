import tempfile
import unittest
from pathlib import Path

from carbon_agent.context import ArtifactStore, ContextWindowManager
from carbon_agent.contracts import AgentRequest, Source
from carbon_agent.execution_store import IdempotencyConflict, SQLiteExecutionStore
from carbon_agent.harness import AgentHarness
from carbon_agent.memory import SQLiteConversationStore
from carbon_agent.planner import FakeToolPlanner, ToolDecision
from carbon_agent.tooling import ToolRegistry, ToolResult, ToolSpec


def tool_registry(handler=None, approval=False, retries=1):
    active_handler = handler or (
        lambda args, context: ToolResult(
            {"fact": "Article 6 governs cooperative approaches."},
            [Source("S1", "policy.pdf", "physical_page:8")],
        )
    )
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="knowledge_search",
            description="search",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=active_handler,
            requires_approval=approval,
            max_retries=retries,
        )
    )
    return registry


class CrashOncePlanner:
    def __init__(self):
        self.calls = 0

    def decide(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("injected planner crash")
        return ToolDecision.finish("恢复后完成。")


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def harness(self, planner, tools=None, max_steps=6):
        return AgentHarness(
            planner=planner,
            tools=tools or tool_registry(),
            execution_store=SQLiteExecutionStore(self.root / "execution.sqlite3"),
            conversation_store=SQLiteConversationStore(self.root / "memory.sqlite3"),
            context_manager=ContextWindowManager(max_characters=1000),
            artifact_store=ArtifactStore(self.root / "artifacts", 200),
            max_steps=max_steps,
        )

    def test_model_driven_tool_loop_and_citation(self):
        planner = FakeToolPlanner(
            [
                ToolDecision.call("knowledge_search", {"query": "Article 6"}),
                ToolDecision.finish("依据本地文件，相关机制见 [S1]。"),
            ]
        )
        response = self.harness(planner).handle(
            AgentRequest("Article 6 是什么", request_id="request-tool-loop")
        )
        self.assertEqual(response.metadata["status"], "completed")
        self.assertTrue(response.metadata["citation_verification"]["passed"])
        self.assertEqual(response.tool_calls[0]["name"], "knowledge_search")
        self.assertEqual(response.sources[0].source_id, "S1")

    def test_invalid_citation_is_rejected(self):
        planner = FakeToolPlanner(
            [
                ToolDecision.call("knowledge_search", {"query": "Article 6"}),
                ToolDecision.finish("模型引用了不存在的来源 [S9]。"),
            ]
        )
        response = self.harness(planner).handle(
            AgentRequest("引用测试", request_id="request-bad-citation")
        )
        self.assertFalse(response.metadata["citation_verification"]["passed"])
        self.assertIn("引用校验未通过", response.answer)

    def test_harness_stops_at_approval_gate(self):
        planner = FakeToolPlanner(
            [ToolDecision.call("knowledge_search", {"query": "sensitive"})]
        )
        response = self.harness(
            planner, tools=tool_registry(approval=True, retries=0)
        ).handle(AgentRequest("敏感操作", request_id="request-approval"))
        self.assertTrue(response.metadata["approval_required"])
        self.assertEqual(response.tool_calls, [])

    def test_idempotent_replay_does_not_call_planner_again(self):
        planner = FakeToolPlanner([ToolDecision.finish("普通回答。")])
        harness = self.harness(planner)
        request = AgentRequest("你好", request_id="request-idempotent")
        first = harness.handle(request)
        second = harness.handle(request)
        self.assertEqual(first.trace_id, second.trace_id)
        self.assertEqual(len(planner.calls), 1)
        self.assertTrue(second.metadata["idempotent_replay"])

    def test_same_id_with_different_payload_is_rejected(self):
        harness = self.harness(FakeToolPlanner([ToolDecision.finish("ok")]))
        harness.handle(AgentRequest("A", request_id="request-conflict"))
        with self.assertRaises(IdempotencyConflict):
            harness.handle(AgentRequest("B", request_id="request-conflict"))

    def test_checkpoint_recovers_after_planner_crash(self):
        planner = CrashOncePlanner()
        harness = self.harness(planner)
        request = AgentRequest("恢复测试", request_id="request-recovery")
        failed = harness.handle(request)
        recovered = harness.handle(request)
        self.assertEqual(failed.metadata["status"], "failed")
        self.assertTrue(recovered.metadata["recovered_from_checkpoint"])
        event_types = [
            event["event_type"] for event in harness.get_events(request.request_id)
        ]
        self.assertIn("execution_failed", event_types)
        self.assertIn("execution_resumed", event_types)

    def test_tool_retries_transient_failure(self):
        calls = {"count": 0}

        def flaky(args, context):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("temporary")
            return ToolResult({}, [])

        planner = FakeToolPlanner(
            [
                ToolDecision.call("knowledge_search", {"query": "x"}),
                ToolDecision.finish("工具已完成。"),
            ]
        )
        response = self.harness(planner, tool_registry(flaky)).handle(
            AgentRequest("重试", request_id="request-retry")
        )
        self.assertEqual(calls["count"], 2)
        self.assertEqual(response.tool_calls[0]["status"], "success")

    def test_max_steps_stops_infinite_tool_loop(self):
        planner = FakeToolPlanner(
            [
                ToolDecision.call("knowledge_search", {"query": "x"}),
                ToolDecision.call("knowledge_search", {"query": "x"}),
            ]
        )
        response = self.harness(planner, max_steps=2).handle(
            AgentRequest("循环", request_id="request-max-step")
        )
        self.assertTrue(response.metadata["max_steps_reached"])


if __name__ == "__main__":
    unittest.main()
