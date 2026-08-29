"""Command-line entry point for local PyCharm terminal use."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .llm import DeepSeekGateway
from .knowledge import ExistingRAGRetriever
from .memory import SQLiteConversationStore
from .v1_simple_qa import SimpleQAAgent
from .v2_conversation import ConversationalAgent
from .v3_knowledge_agent import KnowledgeAgent
from .bootstrap import create_default_orchestrator
from .contracts import AgentRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carbon-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ask_parser = subparsers.add_parser("ask", help="V1 stateless question answering")
    ask_parser.add_argument("question")

    chat_parser = subparsers.add_parser("chat", help="V2 multi-turn conversation")
    chat_parser.add_argument("question")
    chat_parser.add_argument("--session-id")
    chat_parser.add_argument(
        "--database",
        default="runtime/agent_memory.sqlite3",
        help="SQLite memory path",
    )

    knowledge_parser = subparsers.add_parser(
        "knowledge", help="V3 grounded knowledge-base question answering"
    )
    knowledge_parser.add_argument("question")
    knowledge_parser.add_argument("--session-id")
    knowledge_parser.add_argument("--top-k", type=int, default=5)
    knowledge_parser.add_argument("--database", default="runtime/agent_memory.sqlite3")

    run_parser = subparsers.add_parser("run", help="Run V5 custom or V6 LangGraph")
    run_parser.add_argument("question")
    run_parser.add_argument("--session-id")
    run_parser.add_argument(
        "--intent",
        choices=["auto", "chat", "knowledge", "registry", "risk_review"],
        default="auto",
    )
    run_parser.add_argument("--project-id")
    run_parser.add_argument("--approval-granted", action="store_true")
    run_parser.add_argument("--request-id")
    run_parser.add_argument("--runtime-directory", default="runtime")
    run_parser.add_argument(
        "--runtime", choices=["langgraph", "custom"], default="langgraph"
    )

    serve_parser = subparsers.add_parser("serve", help="Start the V6 FastAPI service")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument(
        "--runtime", choices=["langgraph", "custom"], default="langgraph"
    )
    subparsers.add_parser("mcp-server", help="Start the stdio MCP tool server")
    return parser


def main() -> None:
    # Registry-only commands must remain usable without optional LLM dependencies.
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv()
    args = build_parser().parse_args()
    if args.command == "ask":
        response = SimpleQAAgent(DeepSeekGateway()).answer(args.question)
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "chat":
        store = SQLiteConversationStore(Path(args.database))
        response = ConversationalAgent(DeepSeekGateway(), store).answer(
            args.question, session_id=args.session_id
        )
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "knowledge":
        store = SQLiteConversationStore(Path(args.database))
        response = KnowledgeAgent(
            DeepSeekGateway(), ExistingRAGRetriever(), store
        ).answer(
            args.question,
            session_id=args.session_id,
            top_k=args.top_k,
        )
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "run":
        payload = {"project_id": args.project_id} if args.project_id else {}
        response = create_default_orchestrator(
            args.runtime_directory, runtime_kind=args.runtime
        ).handle(
            AgentRequest(
                text=args.question,
                session_id=args.session_id,
                intent=args.intent,
                payload=payload,
                approval_granted=args.approval_granted,
                **({"request_id": args.request_id} if args.request_id else {}),
            )
        )
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "serve":
        try:
            import uvicorn
        except ImportError as error:
            raise RuntimeError("启动服务需要安装 uvicorn。") from error
        os.environ["AGENT_RUNTIME"] = args.runtime
        uvicorn.run("carbon_agent.api:app", host=args.host, port=args.port)
    elif args.command == "mcp-server":
        from .mcp_server import run_stdio

        run_stdio()


if __name__ == "__main__":
    main()
