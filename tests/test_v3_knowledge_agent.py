import tempfile
import unittest
from pathlib import Path

from carbon_agent.knowledge import Evidence
from carbon_agent.llm import FakeGateway
from carbon_agent.memory import SQLiteConversationStore
from carbon_agent.v3_knowledge_agent import ABSTENTION_MESSAGE, KnowledgeAgent


class StubRetriever:
    def __init__(self, evidence: list[Evidence]) -> None:
        self.evidence = evidence
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 5) -> list[Evidence]:
        self.calls.append((query, top_k))
        return self.evidence[:top_k]


def sample_evidence() -> list[Evidence]:
    return [
        Evidence(
            evidence_id="S1",
            text="项目业主申请项目登记时，应当提交项目设计文件。",
            source_file="管理办法.pdf",
            page_number=6,
            document_type="official_rule",
            language="zh",
            score=0.92,
        )
    ]


class KnowledgeAgentTests(unittest.TestCase):
    def test_valid_grounded_answer_keeps_source(self) -> None:
        gateway = FakeGateway(["申请时应提交项目设计文件。[S1]"])
        retriever = StubRetriever(sample_evidence())
        response = KnowledgeAgent(gateway, retriever).answer("需要什么材料？")

        self.assertEqual(response.answer, "申请时应提交项目设计文件。[S1]")
        self.assertEqual(response.sources[0].locator, "physical_page:6")
        self.assertTrue(response.metadata["grounding_audit"]["is_valid"])
        self.assertIn("本轮检索证据", gateway.calls[0][-1].content)

    def test_invalid_citation_is_safely_downgraded(self) -> None:
        gateway = FakeGateway(["需要项目设计文件。[S9]"])
        response = KnowledgeAgent(
            gateway, StubRetriever(sample_evidence())
        ).answer("需要什么材料？")

        self.assertEqual(response.answer, ABSTENTION_MESSAGE)
        self.assertEqual(
            response.metadata["grounding_audit"]["invalid_citations"], ["[S9]"]
        )

    def test_empty_retrieval_abstains_without_calling_llm(self) -> None:
        gateway = FakeGateway([])
        response = KnowledgeAgent(gateway, StubRetriever([])).answer("未知问题")

        self.assertEqual(response.answer, ABSTENTION_MESSAGE)
        self.assertEqual(gateway.calls, [])

    def test_memory_is_context_not_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteConversationStore(Path(directory) / "memory.sqlite3")
            gateway = FakeGateway(["第一轮回答。[S1]", "第二轮回答。[S1]"])
            agent = KnowledgeAgent(gateway, StubRetriever(sample_evidence()), store)
            first = agent.answer("第一轮")
            second = agent.answer("那第二轮呢？", session_id=first.session_id)

            self.assertEqual(second.metadata["evidence_count"], 1)
            self.assertIn("第一轮回答。[S1]", [m.content for m in gateway.calls[1]])


if __name__ == "__main__":
    unittest.main()

