import unittest

from carbon_agent.mcp_server import MCPToolServer
from carbon_agent.tooling import ToolRegistry, ToolResult, ToolSpec


class MCPTests(unittest.TestCase):
    def setUp(self):
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                "registry_lookup",
                "lookup",
                {
                    "type": "object",
                    "properties": {"project_id": {"type": "string"}},
                    "required": ["project_id"],
                },
                lambda args, context: ToolResult({"id": args["project_id"]}),
            )
        )
        registry.register(
            ToolSpec(
                "experimental_risk_review",
                "risk",
                {"type": "object", "properties": {}},
                lambda args, context: ToolResult({}),
            )
        )
        self.server = MCPToolServer(registry)

    def test_only_read_only_tools_are_exposed(self):
        response = self.server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, ["registry_lookup"])

    def test_tool_call_returns_structured_content(self):
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "registry_lookup",
                    "arguments": {"project_id": "P1"},
                },
            }
        )
        self.assertEqual(
            response["result"]["structuredContent"]["result"]["id"], "P1"
        )

    def test_risk_tool_cannot_be_called_through_mcp(self):
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "experimental_risk_review", "arguments": {}},
            }
        )
        self.assertIn("error", response)


if __name__ == "__main__":
    unittest.main()
