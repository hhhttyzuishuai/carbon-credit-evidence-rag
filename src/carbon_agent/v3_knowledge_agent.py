"""V3: grounded knowledge agent with strict citation validation."""

from __future__ import annotations

import re

from .contracts import AgentResponse, Message, Source
from .knowledge import Evidence, KnowledgeRetriever
from .llm import ChatGateway
from .memory import SQLiteConversationStore


ABSTENTION_MESSAGE = "证据不足，需要人工复核。"
CITATION_PATTERN = re.compile(r"\[S(\d+)\]")

V3_SYSTEM_PROMPT = """你是碳信用披露知识专家。
只能依据“本轮检索证据”回答，历史对话只能用于理解指代，不能作为事实证据。
每个关键事实后必须标注 [S1]、[S2] 等本轮证据编号。
不得编造文件、页码、数字或法规结论；证据不足时只回答“证据不足，需要人工复核。”
不得判断任何企业是否绿洗、违法或合规。使用与用户问题相同的语言。"""


def format_evidence(evidence: list[Evidence]) -> str:
    return "\n\n".join(
        (
            f"{item.citation} {item.source_file}，第 {item.page_number} 页，"
            f"{item.document_type}\n{item.text}"
        )
        for item in evidence
    )


def audit_grounding(answer: str, evidence: list[Evidence]) -> dict:
    valid = {item.citation for item in evidence}
    cited = list(
        dict.fromkeys(f"[S{number}]" for number in CITATION_PATTERN.findall(answer))
    )
    invalid = [citation for citation in cited if citation not in valid]
    abstained = ABSTENTION_MESSAGE in answer
    return {
        "is_valid": not invalid and (abstained or bool(cited)),
        "is_abstention": abstained,
        "cited_citations": cited,
        "invalid_citations": invalid,
    }


class KnowledgeAgent:
    name = "knowledge_agent"

    def __init__(
        self,
        gateway: ChatGateway,
        retriever: KnowledgeRetriever,
        store: SQLiteConversationStore | None = None,
        history_limit: int = 8,
    ) -> None:
        self.gateway = gateway
        self.retriever = retriever
        self.store = store
        self.history_limit = history_limit

    def answer(
        self,
        question: str,
        session_id: str | None = None,
        top_k: int = 5,
    ) -> AgentResponse:
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("问题不能为空。")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0。")

        resolved_session_id = None
        history: list[Message] = []
        if self.store is not None:
            resolved_session_id = self.store.create_session(session_id)
            history = self.store.get_history(
                resolved_session_id, limit=self.history_limit
            )

        evidence = self.retriever.retrieve(cleaned_question, top_k=top_k)
        sources = [
            Source(
                source_id=item.evidence_id,
                label=item.source_file,
                locator=f"physical_page:{item.page_number}",
                preview=item.text[:500],
            )
            for item in evidence
        ]

        if not evidence:
            answer = ABSTENTION_MESSAGE
            audit = audit_grounding(answer, evidence)
        else:
            messages = [
                Message(role="system", content=V3_SYSTEM_PROMPT),
                *history,
                Message(
                    role="user",
                    content=(
                        f"用户问题：{cleaned_question}\n\n"
                        f"本轮检索证据：\n{format_evidence(evidence)}\n\n"
                        "请仅依据本轮证据回答，并标注证据编号。"
                    ),
                ),
            ]
            candidate_answer = self.gateway.complete(messages).strip()
            audit = audit_grounding(candidate_answer, evidence)
            answer = candidate_answer if audit["is_valid"] else ABSTENTION_MESSAGE

        if self.store is not None and resolved_session_id is not None:
            self.store.record_turn(resolved_session_id, cleaned_question, answer)

        return AgentResponse(
            answer=answer,
            agent=self.name,
            session_id=resolved_session_id,
            sources=sources,
            metadata={
                "version": "v3",
                "memory_enabled": self.store is not None,
                "evidence_count": len(evidence),
                "grounding_audit": audit,
            },
        )

