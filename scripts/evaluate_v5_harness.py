"""Deterministic V5 harness regression: routing, completion, steps, recovery."""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from carbon_agent.context import ArtifactStore, ContextWindowManager
from carbon_agent.contracts import AgentRequest, Source
from carbon_agent.execution_store import SQLiteExecutionStore
from carbon_agent.harness import AgentHarness
from carbon_agent.memory import SQLiteConversationStore
from carbon_agent.planner import ToolDecision
from carbon_agent.tooling import ToolRegistry, ToolResult, ToolSpec


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "eval" / "v5_tool_cases.jsonl"


class RegressionPlanner:
    def decide(self, messages, tools):
        latest = messages[-1].content
        if "工具 knowledge_search 的执行结果" in latest:
            return ToolDecision.finish("本地证据支持该回答 [S1]。")
        if "工具 registry_lookup 的执行结果" in latest:
            return ToolDecision.finish("本地登记快照匹配该项目 [T1]。")
        if "工具 experimental_risk_review 的执行结果" in latest:
            return ToolDecision.finish("已生成实验性审核信号，不构成合规结论。")
        user = next(
            message.content for message in reversed(messages) if message.role == "user"
        )
        if any(word in user for word in ("风险审核", "风险信号", "语气风险")):
            return ToolDecision.call(
                "experimental_risk_review",
                {
                    "project_id": "VCS1529",
                    "claim_context": "evaluation",
                    "claim_tone": "neutral",
                },
            )
        if any(word in user for word in ("登记", "Project ID", "registry")):
            return ToolDecision.call("registry_lookup", {"project_id": "VCS1529"})
        if any(
            word in user
            for word in (
                "Article 6.2",
                "corresponding adjustment",
                "VCMI",
                "完整性原则",
            )
        ):
            return ToolDecision.call("knowledge_search", {"query": user})
        return ToolDecision.finish("可以进行证据检索、登记查询和受控风险审核。")


class CrashOncePlanner:
    def __init__(self):
        self.crashed = False

    def decide(self, messages, tools):
        if not self.crashed:
            self.crashed = True
            raise RuntimeError("injected")
        return ToolDecision.finish("已从检查点恢复并完成。")


def registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        ToolSpec(
            "knowledge_search",
            "search",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            lambda args, context: ToolResult(
                {"evidence": "fixture"}, [Source("S1", "fixture.pdf", "page:1")]
            ),
        )
    )
    tools.register(
        ToolSpec(
            "registry_lookup",
            "lookup",
            {
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
                "required": ["project_id"],
            },
            lambda args, context: ToolResult(
                {"project": args["project_id"]}, [Source("T1", "fixture.xlsx")]
            ),
        )
    )
    tools.register(
        ToolSpec(
            "experimental_risk_review",
            "risk",
            {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "claim_context": {"type": "string"},
                    "claim_tone": {"type": "string"},
                },
                "required": ["project_id", "claim_context", "claim_tone"],
            },
            lambda args, context: ToolResult({"signal": "fixture"}),
            requires_approval=True,
        )
    )
    return tools


def make_harness(root: Path, planner) -> AgentHarness:
    return AgentHarness(
        planner=planner,
        tools=registry(),
        execution_store=SQLiteExecutionStore(root / "executions.sqlite3"),
        conversation_store=SQLiteConversationStore(root / "memory.sqlite3"),
        context_manager=ContextWindowManager(),
        artifact_store=ArtifactStore(root / "artifacts"),
    )


def load_cases():
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    cases = load_cases()
    latencies = []
    steps = []
    selected_correctly = 0
    completed = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        harness = make_harness(root, RegressionPlanner())
        for case in cases:
            started = time.perf_counter()
            response = harness.handle(
                AgentRequest(
                    case["question"],
                    request_id=f"eval-{case['case_id']}",
                    approval_granted=case.get("approval_granted", False),
                )
            )
            latencies.append((time.perf_counter() - started) * 1000)
            actual = response.tool_calls[0]["name"] if response.tool_calls else None
            selected_correctly += actual == case["expected_tool"]
            completed += response.metadata.get("status") == "completed"
            steps.append(response.metadata.get("steps", 0))

        recovered = 0
        recovery_trials = 4
        for index in range(recovery_trials):
            recovery = make_harness(root / f"recovery-{index}", CrashOncePlanner())
            request = AgentRequest("恢复", request_id=f"recovery-{index}")
            recovery.handle(request)
            response = recovery.handle(request)
            recovered += bool(response.metadata.get("recovered_from_checkpoint"))

    metrics = {
        "cases": len(cases),
        "tool_selection_accuracy": round(selected_correctly / len(cases), 3),
        "task_completion_rate": round(completed / len(cases), 3),
        "average_steps": round(statistics.mean(steps), 3),
        "checkpoint_recovery_rate": round(recovered / recovery_trials, 3),
        "median_local_latency_ms": round(statistics.median(latencies), 2),
        "scope": "deterministic offline regression; not live-model quality",
    }
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if selected_correctly != len(cases) or completed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
