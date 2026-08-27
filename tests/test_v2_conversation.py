import tempfile
import unittest
from pathlib import Path

from carbon_agent.llm import FakeGateway
from carbon_agent.memory import SQLiteConversationStore
from carbon_agent.v2_conversation import ConversationalAgent


class ConversationAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "memory.sqlite3"
        self.store = SQLiteConversationStore(database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_second_turn_receives_first_turn_history(self) -> None:
        gateway = FakeGateway(["它是 CCER。", "这里的“它”指 CCER。"])
        agent = ConversationalAgent(gateway, self.store)

        first = agent.answer("记住：这个机制叫 CCER。")
        second = agent.answer("它叫什么？", session_id=first.session_id)

        sent_contents = [message.content for message in gateway.calls[1]]
        self.assertIn("记住：这个机制叫 CCER。", sent_contents)
        self.assertIn("它是 CCER。", sent_contents)
        self.assertEqual(second.metadata["history_messages_used"], 2)

    def test_history_window_is_bounded(self) -> None:
        gateway = FakeGateway(["a1", "a2", "a3"])
        agent = ConversationalAgent(gateway, self.store, history_limit=2)
        first = agent.answer("q1")
        agent.answer("q2", session_id=first.session_id)
        third = agent.answer("q3", session_id=first.session_id)

        self.assertEqual(third.metadata["history_messages_used"], 2)
        sent_contents = [message.content for message in gateway.calls[2]]
        self.assertNotIn("q1", sent_contents)
        self.assertIn("q2", sent_contents)

    def test_failed_model_call_does_not_persist_half_turn(self) -> None:
        gateway = FakeGateway([])
        agent = ConversationalAgent(gateway, self.store)
        session_id = self.store.create_session("stable-session")

        with self.assertRaises(RuntimeError):
            agent.answer("这轮会失败", session_id=session_id)

        self.assertEqual(self.store.get_history(session_id), [])


if __name__ == "__main__":
    unittest.main()

