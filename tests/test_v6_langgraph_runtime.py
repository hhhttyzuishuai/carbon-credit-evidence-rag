import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from carbon_agent.context import ArtifactStore, ContextWindowManager
from carbon_agent.contracts import AgentRequest, Source
from carbon_agent.execution_store import SQLiteExecutionStore
from carbon_agent.langchain_adapter import (
    LangChainDeepSeekPlanner,
    langchain_tool_from_spec,
)
from carbon_agent.langgraph_runtime import LangGraphAgentRuntime
from carbon_agent.memory import SQLiteConversationStore
from carbon_agent.planner import FakeToolPlanner, ToolDecision
from carbon_agent.tooling import ToolRegistry, ToolResult, ToolSpec


def build_tools(approval=False):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "knowledge_search",
            "Search grounded evidence.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            lambda args, context: ToolResult(
                {"fact": "fixture"},
                [Source("S1", "fixture.pdf", "physical_page:1")],
            ),
            requires_approval=approval,
        )
    )
    return registry


class CrashOncePlanner:
    def __init__(self):
        self.calls = 0

    def decide(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("injected")
        return ToolDecision.finish("恢复完成。")


class FakeLangChainModel:
    def __init__(self):
        self.bound_tools = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "knowledge_search",
                    "args": {"query": "Article 6"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )


class LangGraphRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def runtime(self, planner, tools=None, max_steps=6):
        return LangGraphAgentRuntime(
            planner=planner,
            tools=tools or build_tools(),
            execution_store=SQLiteExecutionStore(self.root / "executions.sqlite3"),
            conversation_store=SQLiteConversationStore(self.root / "memory.sqlite3"),
            context_manager=ContextWindowManager(max_characters=1000),
            artifact_store=ArtifactStore(self.root / "artifacts", 200),
            checkpointer=InMemorySaver(),
            max_steps=max_steps,
        )

    def test_graph_executes_tool_and_verifier_nodes(self):
        runtime = self.runtime(
            FakeToolPlanner(
                [
                    ToolDecision.call("knowledge_search", {"query": "Article 6"}),
                    ToolDecision.finish("依据证据回答 [S1]。"),
                ]
            )
        )
        response = runtime.handle(
            AgentRequest("Article 6", request_id="v6-tool-loop")
        )
        self.assertEqual(response.agent, "v6_langgraph_agent")
        self.assertEqual(response.metadata["runtime"], "langgraph")
        self.assertTrue(response.metadata["citation_verification"]["passed"])
        self.assertEqual(response.tool_calls[0]["executor"], "langchain_structured_tool")
        events = runtime.get_events("v6-tool-loop")
        nodes = {
            event["payload"].get("node")
            for event in events
            if event["event_type"] == "langgraph_node_completed"
        }
        self.assertEqual(nodes, {"planner", "tool_executor", "output_verifier"})

    def test_graph_architecture_is_introspectable(self):
        runtime = self.runtime(FakeToolPlanner([ToolDecision.finish("ok")]))
        architecture = runtime.get_architecture()
        self.assertEqual(
            architecture["nodes"], ["planner", "tool_executor", "output_verifier"]
        )
        self.assertIn("flowchart", architecture["mermaid"])

    def test_completed_graph_request_is_idempotent(self):
        planner = FakeToolPlanner([ToolDecision.finish("普通回答。")])
        runtime = self.runtime(planner)
        request = AgentRequest("你好", request_id="v6-idempotent")
        first = runtime.handle(request)
        second = runtime.handle(request)
        self.assertEqual(first.trace_id, second.trace_id)
        self.assertTrue(second.metadata["idempotent_replay"])
        self.assertEqual(len(planner.calls), 1)

    def test_graph_resumes_failed_planner_node(self):
        planner = CrashOncePlanner()
        runtime = self.runtime(planner)
        request = AgentRequest("恢复", request_id="v6-recovery")
        failed = runtime.handle(request)
        recovered = runtime.handle(request)
        self.assertEqual(failed.metadata["status"], "failed")
        self.assertEqual(recovered.answer, "恢复完成。")
        self.assertTrue(recovered.metadata["recovered_from_checkpoint"])

    def test_graph_enforces_approval_before_langchain_tool(self):
        runtime = self.runtime(
            FakeToolPlanner(
                [ToolDecision.call("knowledge_search", {"query": "sensitive"})]
            ),
            tools=build_tools(approval=True),
        )
        response = runtime.handle(
            AgentRequest("敏感查询", request_id="v6-approval")
        )
        self.assertEqual(response.metadata["status"], "approval_required")
        self.assertEqual(response.tool_calls, [])

    def test_langchain_structured_tool_preserves_schema_and_executes(self):
        spec = build_tools().get("knowledge_search")
        tool = langchain_tool_from_spec(spec, lambda args: {"query": args["query"]})
        self.assertEqual(tool.name, "knowledge_search")
        self.assertIn("query", tool.args_schema.model_fields)
        self.assertEqual(tool.invoke({"query": "test"}), {"query": "test"})
        with self.assertRaises(Exception):
            tool.invoke({"query": "test", "unexpected": "blocked"})

    def test_langchain_deepseek_planner_reads_standard_tool_call(self):
        model = FakeLangChainModel()
        planner = LangChainDeepSeekPlanner(model=model)
        decision = planner.decide([], build_tools().list_specs())
        self.assertEqual(decision.tool_name, "knowledge_search")
        self.assertEqual(decision.arguments, {"query": "Article 6"})
        self.assertEqual(model.bound_tools[0].name, "knowledge_search")


if __name__ == "__main__":
    unittest.main()
