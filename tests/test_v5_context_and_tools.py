import tempfile
import unittest
from pathlib import Path

from carbon_agent.context import ArtifactStore, ContextWindowManager
from carbon_agent.contracts import Message
from carbon_agent.tooling import (
    ToolApprovalRequired,
    ToolContext,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolValidationError,
)


class ContextAndToolTests(unittest.TestCase):
    def test_context_is_compacted_with_recent_turns_preserved(self):
        messages = [Message("system", "rules")] + [
            Message("user", str(index) * 300) for index in range(8)
        ]
        result = ContextWindowManager(1000, recent_messages=2).compact(messages)
        self.assertGreater(result.compacted_messages, 0)
        self.assertLessEqual(result.final_characters, 1000)
        self.assertIn("7", result.messages[-1].content)

    def test_large_tool_output_is_externalized_with_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ArtifactStore(Path(directory), 30).externalize(
                "request", 1, {"content": "x" * 200}
            )
            self.assertIsNotNone(result.artifact)
            self.assertTrue(Path(result.artifact["path"]).exists())
            self.assertEqual(len(result.artifact["sha256"]), 64)

    def test_registry_validates_schema_and_approval(self):
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                "dangerous",
                "test",
                {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
                lambda args, context: ToolResult({"ok": True}),
                requires_approval=True,
            )
        )
        context = ToolContext("actor", "request", False)
        with self.assertRaises(ToolValidationError):
            registry.execute("dangerous", {}, context)
        with self.assertRaises(ToolApprovalRequired):
            registry.execute("dangerous", {"id": "1"}, context)
        result = registry.execute(
            "dangerous", {"id": "1"}, ToolContext("actor", "request", True)
        )
        self.assertTrue(result.content["ok"])


if __name__ == "__main__":
    unittest.main()
