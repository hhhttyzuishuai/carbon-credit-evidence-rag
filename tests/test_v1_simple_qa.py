import unittest

from carbon_agent.llm import FakeGateway
from carbon_agent.v1_simple_qa import SimpleQAAgent


class SimpleQAAgentTests(unittest.TestCase):
    def test_returns_structured_response(self) -> None:
        gateway = FakeGateway(["碳信用是一种可交易的减排量凭证。"])
        response = SimpleQAAgent(gateway).answer("什么是碳信用？")

        self.assertEqual(response.agent, "simple_qa_agent")
        self.assertIn("碳信用", response.answer)
        self.assertEqual(response.metadata["version"], "v1")
        self.assertFalse(response.metadata["memory_enabled"])
        self.assertEqual(gateway.calls[0][-1].content, "什么是碳信用？")

    def test_rejects_blank_question(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能为空"):
            SimpleQAAgent(FakeGateway()).answer("   ")

    def test_rejects_empty_model_output(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "空回答"):
            SimpleQAAgent(FakeGateway(["  "])).answer("测试")


if __name__ == "__main__":
    unittest.main()

