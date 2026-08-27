"""Knowledge retrieval contracts and adapter for the existing bilingual RAG."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    text: str
    source_file: str
    page_number: int
    document_type: str
    language: str
    score: float | None = None

    @property
    def citation(self) -> str:
        return f"[{self.evidence_id}]"


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: str, top_k: int = 5) -> list[Evidence]:
        """Return ranked, traceable evidence for a query."""


class ExistingRAGRetriever:
    """Reuse the project's Hybrid top-20 + Cross-Encoder top-k pipeline."""

    def retrieve(self, query: str, top_k: int = 5) -> list[Evidence]:
        # Lazy imports keep V1/V2 and their tests independent from GPU dependencies.
        from step_09_hybrid_retriever import hybrid_search
        from step_10_reranker import rerank

        candidates = hybrid_search(query=query, top_k=20, candidate_k=20)
        results = rerank(query=query, candidates=candidates, top_k=top_k)

        evidence: list[Evidence] = []
        for index, result in enumerate(results, start=1):
            chunk = result["chunk"]
            evidence.append(
                Evidence(
                    evidence_id=f"S{index}",
                    text=chunk["text"],
                    source_file=chunk["source_file"],
                    page_number=int(chunk["page_number"]),
                    document_type=chunk["document_type"],
                    language=chunk["language"],
                    score=float(result["rerank_score"]),
                )
            )
        return evidence

