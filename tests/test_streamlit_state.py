import unittest
from unittest.mock import Mock

from carbon_agent.streamlit_app import _begin_new_request


class StreamlitStateTests(unittest.TestCase):
    def test_begin_new_request_rotates_id_and_clears_stale_result(self) -> None:
        state = {
            "session_id": "same-conversation",
            "request_id": "old-request",
            "last_response": {"answer": "old"},
            "last_events": [{"event_type": "completed"}],
        }
        request_id = Mock(hex="new-request")

        _begin_new_request(state, lambda: request_id)

        self.assertEqual(state["request_id"], "new-request")
        self.assertEqual(state["session_id"], "same-conversation")
        self.assertNotIn("last_response", state)
        self.assertNotIn("last_events", state)


if __name__ == "__main__":
    unittest.main()
