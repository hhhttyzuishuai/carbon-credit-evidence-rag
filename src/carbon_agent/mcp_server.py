"""Small, dependency-free MCP stdio adapter for read-only V5 tools."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any, TextIO
from uuid import uuid4

from .knowledge import ExistingRAGRetriever
from .tooling import ToolContext, ToolRegistry, build_default_tool_registry


MCP_PROTOCOL_VERSION = "2025-06-18"
EXPOSED_TOOLS = {"knowledge_search", "registry_lookup"}


class MCPToolServer:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None and method and method.startswith("notifications/"):
            return None
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "carbon-credit-agent-tools",
                        "version": "5.0.0",
                    },
                }
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": spec.name,
                            "description": spec.description,
                            "inputSchema": spec.parameters,
                        }
                        for spec in self.registry.list_specs()
                        if spec.name in EXPOSED_TOOLS
                    ]
                }
            elif method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                if name not in EXPOSED_TOOLS:
                    raise ValueError(f"MCP 不允许调用工具：{name}")
                tool_result = self.registry.execute(
                    name,
                    params.get("arguments", {}),
                    ToolContext(
                        actor_id="mcp-client",
                        request_id=uuid4().hex,
                        approval_granted=False,
                    ),
                )
                structured = {
                    "result": tool_result.content,
                    "sources": [asdict(source) for source in tool_result.sources],
                    "metadata": tool_result.metadata,
                }
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(structured, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": structured,
                    "isError": False,
                }
            elif method == "ping":
                result = {}
            else:
                return self._error(request_id, -32601, f"未知方法：{method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as error:
            return self._error(
                request_id,
                -32602,
                str(error),
                {"error_type": type(error).__name__},
            )

    @staticmethod
    def _error(
        request_id: Any,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}


def run_stdio(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> None:
    server = MCPToolServer(build_default_tool_registry(ExistingRAGRetriever()))
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = server.handle(request)
        except json.JSONDecodeError as error:
            response = MCPToolServer._error(None, -32700, str(error))
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()


if __name__ == "__main__":
    run_stdio()
