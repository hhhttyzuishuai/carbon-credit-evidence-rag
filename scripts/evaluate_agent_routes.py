"""Evaluate deterministic routing on the committed regression set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from carbon_agent.contracts import AgentRequest  # noqa: E402
from carbon_agent.routing import RouterAgent  # noqa: E402


DEFAULT_CASES = PROJECT_ROOT / "data" / "eval" / "agent_routing_cases.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "agent_route_evaluation.json"


def load_cases(path: Path) -> list[dict]:
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        raise ValueError("Agent 路由评测集为空。")
    return cases


def evaluate(cases: list[dict]) -> dict:
    router = RouterAgent()
    details = []
    correct = 0
    for case in cases:
        predicted = router.route(
            AgentRequest(
                text=case["text"],
                intent=case.get("intent", "auto"),
                payload=case.get("payload", {}),
            )
        )
        passed = predicted == case["expected_route"]
        correct += int(passed)
        details.append(
            {
                "case_id": case["case_id"],
                "expected_route": case["expected_route"],
                "predicted_route": predicted,
                "passed": passed,
            }
        )

    return {
        "case_count": len(cases),
        "correct_count": correct,
        "route_accuracy": correct / len(cases),
        "important_note": (
            "This is a committed regression set for known intents, not evidence of "
            "open-domain routing generalization."
        ),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = evaluate(load_cases(args.cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"route_accuracy={report['route_accuracy']:.3f} "
        f"({report['correct_count']}/{report['case_count']})"
    )
    print(f"report={args.output}")


if __name__ == "__main__":
    main()
