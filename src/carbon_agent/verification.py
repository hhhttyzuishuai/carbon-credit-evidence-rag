"""Shared output-policy checks used by the custom and LangGraph runtimes."""

from __future__ import annotations

import re
from typing import Any, Sequence

from .contracts import Source


def verify_grounded_answer(
    answer: str,
    tool_calls: Sequence[dict[str, Any]],
    sources: Sequence[Source],
) -> tuple[str, dict[str, Any]]:
    evidence_tools = {
        call["name"]
        for call in tool_calls
        if call.get("status") == "success"
        and call.get("name") in {"knowledge_search", "registry_lookup"}
    }
    valid_ids = {source.source_id for source in sources}
    cited_ids = set(re.findall(r"\[([ST]\d+)\]", answer))
    invalid = sorted(cited_ids - valid_ids)
    missing = bool(evidence_tools and valid_ids and not (cited_ids & valid_ids))
    passed = not invalid and not missing
    if not passed:
        answer = (
            "输出引用校验未通过，系统没有把该回答作为可靠结论返回。"
            f"可用证据编号：{', '.join(sorted(valid_ids)) or '无'}。"
        )
    return answer, {
        "passed": passed,
        "valid_source_ids": sorted(valid_ids),
        "cited_source_ids": sorted(cited_ids),
        "invalid_source_ids": invalid,
        "missing_required_citation": missing,
    }
