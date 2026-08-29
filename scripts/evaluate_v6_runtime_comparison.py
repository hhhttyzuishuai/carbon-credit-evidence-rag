"""Compare V5 custom Harness and V6 LangGraph on the same offline fixtures."""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from carbon_agent.context import ArtifactStore, ContextWindowManager
from carbon_agent.contracts import AgentRequest
from carbon_agent.execution_store import SQLiteExecutionStore
from carbon_agent.langgraph_runtime import LangGraphAgentRuntime
from carbon_agent.memory import SQLiteConversationStore
from evaluate_v5_harness import (
    CASES,
    CrashOncePlanner,
    RegressionPlanner,
    load_cases,
    make_harness,
    registry,
)


def make_langgraph(root: Path, planner) -> LangGraphAgentRuntime:
    return LangGraphAgentRuntime(
        planner=planner,
        tools=registry(),
        execution_store=SQLiteExecutionStore(root / "executions.sqlite3"),
        conversation_store=SQLiteConversationStore(root / "memory.sqlite3"),
        context_manager=ContextWindowManager(),
        artifact_store=ArtifactStore(root / "artifacts"),
        checkpointer=InMemorySaver(),
    )


def evaluate_runtime(name: str, runtime, cases: list[dict]) -> dict:
    selected_correctly = 0
    completed = 0
    steps = []
    latencies = []
    for case in cases:
        started = time.perf_counter()
        response = runtime.handle(
            AgentRequest(
                case["question"],
                request_id=f"{name}-{case['case_id']}",
                approval_granted=case.get("approval_granted", False),
            )
        )
        latencies.append((time.perf_counter() - started) * 1000)
        actual = response.tool_calls[0]["name"] if response.tool_calls else None
        selected_correctly += actual == case["expected_tool"]
        completed += response.metadata.get("status") == "completed"
        steps.append(response.metadata.get("steps", 0))
    return {
        "runtime": name,
        "cases": len(cases),
        "tool_selection_accuracy": round(selected_correctly / len(cases), 3),
        "task_completion_rate": round(completed / len(cases), 3),
        "average_steps": round(statistics.mean(steps), 3),
        "median_local_latency_ms": round(statistics.median(latencies), 2),
    }


def recovery_rate(factory, root: Path, name: str, trials: int = 4) -> float:
    recovered = 0
    for index in range(trials):
        runtime = factory(root / f"{name}-recovery-{index}", CrashOncePlanner())
        request = AgentRequest("恢复", request_id=f"{name}-recovery-{index}")
        runtime.handle(request)
        response = runtime.handle(request)
        recovered += bool(response.metadata.get("recovered_from_checkpoint"))
    return round(recovered / trials, 3)


def main() -> None:
    cases = load_cases()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        custom = evaluate_runtime(
            "v5_custom",
            make_harness(root / "v5", RegressionPlanner()),
            cases,
        )
        langgraph = evaluate_runtime(
            "v6_langgraph",
            make_langgraph(root / "v6", RegressionPlanner()),
            cases,
        )
        custom["checkpoint_recovery_rate"] = recovery_rate(
            make_harness, root, "v5"
        )
        langgraph["checkpoint_recovery_rate"] = recovery_rate(
            make_langgraph, root, "v6"
        )

    report = {
        "dataset": str(CASES.relative_to(Path(__file__).resolve().parents[1])),
        "comparison": [custom, langgraph],
        "scope": (
            "Deterministic Fake Planner/Tool regression. Latency measures local "
            "orchestration overhead only, not live LLM or GPU retrieval."
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for result in report["comparison"]:
        if (
            result["tool_selection_accuracy"] != 1.0
            or result["task_completion_rate"] != 1.0
            or result["checkpoint_recovery_rate"] != 1.0
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
