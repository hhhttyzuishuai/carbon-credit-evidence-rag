"""Command-line entry point for local PyCharm terminal use."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .llm import DeepSeekGateway
from .memory import SQLiteConversationStore
from .v1_simple_qa import SimpleQAAgent
from .v2_conversation import ConversationalAgent


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
    return parser


def main() -> None:
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


if __name__ == "__main__":
    main()
