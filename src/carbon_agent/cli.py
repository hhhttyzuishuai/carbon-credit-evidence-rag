"""Command-line entry point for local PyCharm terminal use."""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

from .llm import DeepSeekGateway
from .v1_simple_qa import SimpleQAAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carbon-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ask_parser = subparsers.add_parser("ask", help="V1 stateless question answering")
    ask_parser.add_argument("question")
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    if args.command == "ask":
        response = SimpleQAAgent(DeepSeekGateway()).answer(args.question)
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

