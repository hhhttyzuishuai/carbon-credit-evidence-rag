"""Business specialist agents with narrow, testable responsibilities."""

from __future__ import annotations

import json
import re
from typing import Any

from .business_tools import RegistryLookup, RiskReviewer
from .contracts import AgentRequest, AgentResponse, Source
from .memory import SQLiteConversationStore
from .routing import PROJECT_ID_PATTERN


def _record_if_enabled(
    store: SQLiteConversationStore | None,
    request: AgentRequest,
    answer: str,
) -> str | None:
    if store is None:
        return request.session_id
    session_id = store.create_session(request.session_id)
    store.record_turn(session_id, request.text, answer)
    return session_id


class RegistryAgent:
    name = "registry_agent"

    def __init__(
        self,
        tool: RegistryLookup,
        store: SQLiteConversationStore | None = None,
    ) -> None:
        self.tool = tool
        self.store = store

    def _project_id(self, request: AgentRequest) -> str | None:
        payload_id = request.payload.get("project_id")
        if payload_id:
            return str(payload_id).strip().upper()
        match = PROJECT_ID_PATTERN.search(request.text)
        return re.sub(r"[- ]", "", match.group(0)).upper() if match else None

    def answer(self, request: AgentRequest) -> AgentResponse:
        project_id = self._project_id(request)
        if not project_id:
            answer = "请提供需要精确查询的 Project ID。"
            return AgentResponse(
                answer=answer,
                agent=self.name,
                session_id=_record_if_enabled(self.store, request, answer),
                metadata={"status": "missing_project_id"},
            )

        record = self.tool.lookup(project_id)
        tool_call = {"tool": "registry_lookup", "project_id": project_id}
        if record is None:
            answer = f"本地登记记录快照中未精确匹配到项目 {project_id}，需要人工复核。"
            return AgentResponse(
                answer=answer,
                agent=self.name,
                session_id=_record_if_enabled(self.store, request, answer),
                tool_calls=[{**tool_call, "status": "not_found"}],
                metadata={"status": "not_found", "snapshot_is_realtime": False},
            )

        answer = (
            f"项目 {project_id}（{record.get('project_name') or '名称未披露'}）的本地快照状态为 "
            f"{record.get('voluntary_status') or '未披露'}；登记机构为 "
            f"{record.get('registry') or '未披露'}；累计签发 "
            f"{record.get('total_credits_issued')!s}、注销 "
            f"{record.get('total_credits_retired')!s}、剩余 "
            f"{record.get('total_credits_remaining')!s}。该结果来自静态快照，不代表实时状态。[T1]"
        )
        source = Source(
            source_id="T1",
            label=str(record.get("source_workbook", "registry snapshot")),
            locator=(
                f"sheet:{record.get('source_sheet')};"
                f"excel_row:{record.get('source_excel_row')}"
            ),
            preview=json.dumps(record, ensure_ascii=False)[:500],
        )
        return AgentResponse(
            answer=answer,
            agent=self.name,
            session_id=_record_if_enabled(self.store, request, answer),
            sources=[source],
            tool_calls=[{**tool_call, "status": "success"}],
            metadata={"status": "success", "snapshot_is_realtime": False},
        )


class RiskReviewAgent:
    name = "risk_review_agent"

    def __init__(
        self,
        tool: RiskReviewer,
        store: SQLiteConversationStore | None = None,
    ) -> None:
        self.tool = tool
        self.store = store

    def answer(self, request: AgentRequest) -> AgentResponse:
        if not request.approval_granted:
            answer = (
                "实验性风险审核需要调用方显式确认。当前未执行模型评分；"
                "请核对输入证据后，将 approval_granted 设为 true。"
            )
            return AgentResponse(
                answer=answer,
                agent=self.name,
                session_id=_record_if_enabled(self.store, request, answer),
                metadata={"status": "approval_required"},
            )

        result = self.tool.review(request.payload)
        review = result["review_result"]
        answer = (
            "风险审核工具已执行，决策状态为 "
            f"{review.get('decision', 'review_required')}。"
            f"{review.get('reason', '')} 本结果不构成绿洗、违法或合规结论。"
        )
        source_payload = review.get("registry_source")
        sources = []
        if source_payload:
            sources.append(
                Source(
                    source_id="T1",
                    label=str(source_payload.get("source_workbook")),
                    locator=(
                        f"sheet:{source_payload.get('source_sheet')};"
                        f"excel_row:{source_payload.get('source_excel_row')}"
                    ),
                )
            )
        return AgentResponse(
            answer=answer,
            agent=self.name,
            session_id=_record_if_enabled(self.store, request, answer),
            sources=sources,
            tool_calls=[{"tool": "experimental_risk_review", "status": "success"}],
            metadata={"status": "success", "risk_review": review},
        )


class OutputVerifierAgent:
    name = "output_verifier_agent"
    allowed_agents = {
        "conversation_agent",
        "knowledge_agent",
        "registry_agent",
        "risk_review_agent",
    }

    def verify(self, route: str, response: AgentResponse) -> AgentResponse:
        issues: list[str] = []
        if response.agent not in self.allowed_agents:
            issues.append("unknown_agent")
        if not response.answer.strip():
            issues.append("empty_answer")
        if route == "knowledge" and "证据不足" not in response.answer:
            if not response.sources:
                issues.append("knowledge_answer_without_sources")
        if route == "registry" and response.metadata.get("status") == "success":
            if not response.sources:
                issues.append("registry_answer_without_source")

        response.metadata["verification"] = {
            "passed": not issues,
            "issues": issues,
            "verifier": self.name,
        }
        if issues:
            response.answer = "系统输出校验未通过，需要人工复核。"
        return response
