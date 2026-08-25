import argparse
import json
import re
from functools import lru_cache
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# BM25 直接读取质量检查通过的 Chunk，不需要单独保存索引文件。
CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_chunks.jsonl"


@lru_cache(maxsize=1)
def load_chunks() -> list[dict]:
    """读取全部 Chunk；同一进程内只读取一次。"""
    with CHUNKS_PATH.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def detect_query_language(query: str) -> str:
    """只要查询中含中文字符，就按中文分词。"""
    if re.search(r"[\u4e00-\u9fff]", query):
        return "zh"

    return "en"


def tokenize(text: str, language: str) -> list[str]:
    """针对中英文使用不同的关键词切分策略。"""
    if language == "zh":
        # jieba 精确模式适合当前的小型中文检索语料。
        return [
            token.strip()
            for token in jieba.lcut(text)
            if token.strip() and not re.fullmatch(r"\W+", token)
        ]

    # 英文保留单词、数字、连字符和英文缩写中的撇号。
    return re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)?", text.lower())


def matches_filters(
    chunk: dict,
    language: str | None,
    document_type: str | None,
    authority_level: str | None,
) -> bool:
    """根据可选元数据过滤候选资料。"""
    return (
        (language is None or chunk["language"] == language)
        and (
            document_type is None
            or chunk["document_type"] == document_type
        )
        and (
            authority_level is None
            or chunk["authority_level"] == authority_level
        )
    )


@lru_cache(maxsize=16)
def build_bm25_index(
    language: str | None,
    document_type: str | None,
    authority_level: str | None,
) -> tuple[list[dict], BM25Okapi | None]:
    """按过滤条件构建并缓存 BM25 索引。"""
    chunks = load_chunks()

    candidates = [
        chunk
        for chunk in chunks
        if matches_filters(
            chunk,
            language=language,
            document_type=document_type,
            authority_level=authority_level,
        )
    ]

    # 没有候选资料时，不构建空 BM25 索引。
    if not candidates:
        return candidates, None

    tokenized_corpus = [
        tokenize(chunk["text"], chunk["language"])
        for chunk in candidates
    ]

    return candidates, BM25Okapi(tokenized_corpus)


def search(
    query: str,
    top_k: int = 5,
    language: str | None = None,
    document_type: str | None = None,
    authority_level: str | None = None,
) -> list[tuple[dict, float]]:
    """用 BM25 返回关键词匹配最好的 Chunk。"""
    candidates, bm25 = build_bm25_index(
        language=language,
        document_type=document_type,
        authority_level=authority_level,
    )

    if not candidates or bm25 is None:
        return []

    # 查询根据自身语言进行分词。
    query_language = detect_query_language(query)
    query_tokens = tokenize(query, query_language)

    scores = bm25.get_scores(query_tokens)

    ranked_indices = sorted(
        range(len(candidates)),
        key=lambda index: scores[index],
        reverse=True,
    )[:top_k]

    return [
        (candidates[index], float(scores[index]))
        for index in ranked_indices
    ]


def main() -> None:
    """提供命令行入口，方便与 Dense Retriever 对比。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--language", choices=["zh", "en"])
    parser.add_argument(
        "--document-type",
        choices=[
            "official_rule",
            "official_market_report",
            "company_disclosure",
            "comment_letter",
        ],
    )
    parser.add_argument(
        "--authority-level",
        choices=[
            "official",
            "company_disclosure",
            "company_opinion",
        ],
    )
    args = parser.parse_args()

    results = search(
        query=args.query,
        top_k=args.top_k,
        language=args.language,
        document_type=args.document_type,
        authority_level=args.authority_level,
    )

    print(f"\n查询：{args.query}")
    print(f"查询分词：{tokenize(args.query, detect_query_language(args.query))}")
    print(f"返回结果数：{len(results)}")

    for rank, (chunk, score) in enumerate(results, start=1):
        print(f"\n--- Top {rank} | BM25 分数：{score:.4f} ---")
        print(
            f"来源：{chunk['source_file']} | "
            f"第 {chunk['page_number']} 页 | "
            f"{chunk['language']} | {chunk['document_type']}"
        )
        print(f"文本：{chunk['text'][:220]}")


if __name__ == "__main__":
    main()