import argparse

import torch
from sentence_transformers import CrossEncoder

from step_09_hybrid_retriever import hybrid_search


# 精排模型：适合中文和英文的 query-document 相关性判断。
MODEL_NAME = "BAAI/bge-reranker-base"


def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    batch_size: int = 8,
) -> list[dict]:
    """对 Hybrid Retrieval 返回的候选 Chunk 进行精细相关性排序。"""
    if not candidates:
        return []

    # 优先用 GPU；没有 GPU 时自动改用 CPU。
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CrossEncoder(MODEL_NAME, device=device)

    # Cross-Encoder 会同时阅读“问题 + 文本”，为每一对生成相关性分数。
    pairs = [(query, item["chunk"]["text"]) for item in candidates]
    scores = model.predict(
        pairs,
        batch_size=batch_size,
        show_progress_bar=False,
    )

    reranked = []
    for item, score in zip(candidates, scores):
        result = item.copy()
        result["rerank_score"] = float(score)
        reranked.append(result)

    # 分数越高，表示模型认为该 Chunk 与问题越相关。
    reranked.sort(key=lambda item: item["rerank_score"], reverse=True)
    return reranked[:top_k]


def main() -> None:
    """命令行入口：Hybrid Retrieval → Reranker。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=20)
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

    # 第一阶段：快速召回候选资料。
    candidates = hybrid_search(
        query=args.query,
        top_k=args.candidate_k,
        candidate_k=args.candidate_k,
        language=args.language,
        document_type=args.document_type,
        authority_level=args.authority_level,
    )

    # 第二阶段：对少量候选进行更准确、但更慢的排序。
    results = rerank(
        query=args.query,
        candidates=candidates,
        top_k=args.top_k,
    )

    print(f"\n查询：{args.query}")
    print(f"精排模型：{MODEL_NAME}")
    print(f"候选数：{len(candidates)}")
    print(f"返回结果数：{len(results)}")

    for rank, result in enumerate(results, start=1):
        chunk = result["chunk"]

        print(f"\n--- Top {rank} | 精排分数：{result['rerank_score']:.4f} ---")
        print(
            f"原 RRF 排名信息：Dense={result['dense_rank']} | "
            f"BM25={result['bm25_rank']}"
        )
        print(
            f"来源：{chunk['source_file']} | 第 {chunk['page_number']} 页 | "
            f"{chunk['language']} | {chunk['document_type']}"
        )
        print(f"文本：{chunk['text'][:300]}")


if __name__ == "__main__":
    main()