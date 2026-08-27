"""Deterministic, auditable intent routing for specialist agents."""

from __future__ import annotations

import re

from .contracts import AgentRequest, Intent


PROJECT_ID_PATTERN = re.compile(r"\b(?:ACR|CAR|VCS|GS|CDM)[- ]?\d+\b", re.I)

RISK_KEYWORDS = ("风险评分", "风险审核", "声明数量", "risk review", "risk score")
REGISTRY_KEYWORDS = ("登记状态", "项目登记表", "registry", "签发量", "注销量", "剩余量")
KNOWLEDGE_KEYWORDS = (
    "依据",
    "证据",
    "规定",
    "管理办法",
    "报告中",
    "pdf",
    "according to",
    "evidence",
)


class RouterAgent:
    name = "router_agent"

    def route(self, request: AgentRequest) -> Intent:
        if request.intent != "auto":
            return request.intent

        normalized = request.text.strip().lower()
        if request.payload.get("action") == "risk_review" or any(
            keyword in normalized for keyword in RISK_KEYWORDS
        ):
            return "risk_review"
        if request.payload.get("project_id") and any(
            keyword in normalized for keyword in REGISTRY_KEYWORDS
        ):
            return "registry"
        if PROJECT_ID_PATTERN.search(request.text) and any(
            keyword in normalized for keyword in REGISTRY_KEYWORDS
        ):
            return "registry"
        if any(keyword in normalized for keyword in KNOWLEDGE_KEYWORDS):
            return "knowledge"
        return "chat"

