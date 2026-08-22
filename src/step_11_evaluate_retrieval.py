import argparse
import json
from pathlib import Path

import torch
from sentence_transformers import CrossEncoder

from step_07_dense_retriever import search as dense_search
from step_08_bm25_retriever import search as bm25_search
from step_09_hybrid_retriever import hybrid_search
from step_10_reranker import MODEL_NAME, rerank


# 统一获得查询所需的语言和元数据过滤条件。
def get_search_kwargs(item: dict) -> dict:
    filters = item.get("filters", {})

    return {
        "language": item.get("language"),
        "document_type": filters.get("document_type"),
        "authority_level": filters.get("authority_level"),
    }


# 用“文件名 + 物理页码”唯一表示一条人工标注证据。
def get_relevant_pages(item: dict) -> set[tuple[str, int]]:
    return {
        (page["source_file"], int(page["page_number"]))
        for page in item["relevant_pages"]
    }


# 判断检索结果中，正确证据第一次出现在哪个名次。
def first_relevant_rank(
    chunks: list[dict],
    relevant_pages: set[tuple[str, int]],
) -> int | None:
    for rank, chunk in enumerate(chunks, start=1):
        page_key = (chunk["source_file"], int(chunk["page_number"]))
        if page_key in relevant_pages:
            return rank

    return None


# 单正确页场景下，Hit@k 表示正确页是否进入前 k 条结果。
def calculate_metrics(rank: int | None) -> dict:
    return {
        "hit_at_1": int(rank == 1),
        "hit_at_3": int(rank is not None and rank <= 3),
        "mrr": 1 / rank if rank is not None else 0.0,
        "first_relevant_rank": rank,
    }


def evaluate_one(item: dict, reranker_model: CrossEncoder) -> dict:
    query = item["query"]
    search_kwargs = get_search_kwargs(item)
    relevant_pages = get_relevant_pages(item)

    # Dense 与 BM25 各自召回前 20 条候选。
    dense_results = dense_search(query=query, top_k=20, **search_kwargs)
    bm25_results = bm25_search(query=query, top_k=20, **search_kwargs)

    dense_chunks = [chunk for chunk, _ in dense_results]
    bm25_chunks = [chunk for chunk, _ in bm25_results]

    # Hybrid 使用 RRF 融合两套候选。
    hybrid_results = hybrid_search(
        query=query,
        top_k=20,
        candidate_k=20,
        **search_kwargs,
    )
    hybrid_chunks = [item["chunk"] for item in hybrid_results]

    # Reranker 对 Hybrid 候选进行精排。
    reranked_results = rerank(
        query=query,
        candidates=hybrid_results,
        top_k=20,
        model=reranker_model,
    )
    reranked_chunks = [item["chunk"] for item in reranked_results]

    return {
        "id": item["id"],
        "query": query,
        "relevant_pages": [
            {"source_file": source_file, "page_number": page_number}
            for source_file, page_number in relevant_pages
        ],
        "dense": calculate_metrics(
            first_relevant_rank(dense_chunks, relevant_pages)
        ),
        "bm25": calculate_metrics(
            first_relevant_rank(bm25_chunks, relevant_pages)
        ),
        "hybrid": calculate_metrics(
            first_relevant_rank(hybrid_chunks, relevant_pages)
        ),
        "reranker": calculate_metrics(
            first_relevant_rank(reranked_chunks, relevant_pages)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--eval-path",
        default="data/eval/gold_queries.jsonl",
    )
    parser.add_argument(
        "--out-path",
        default="outputs/retrieval_evaluation.json",
    )
    args = parser.parse_args()

    # 读取人工标注的金标准问题。
    with open(args.eval_path, encoding="utf-8") as file:
        eval_items = [
            json.loads(line)
            for line in file
            if line.strip()
        ]

    # 整个评估过程只加载一次精排模型。
    device = "cuda" if torch.cuda.is_available() else "cpu"
    reranker_model = CrossEncoder(MODEL_NAME, device=device)

    results = [
        evaluate_one(item, reranker_model)
        for item in eval_items
    ]

    methods = ["dense", "bm25", "hybrid", "reranker"]
    summary = {}

    for method in methods:
        summary[method] = {
            "hit_at_1": sum(item[method]["hit_at_1"] for item in results) / len(results),
            "hit_at_3": sum(item[method]["hit_at_3"] for item in results) / len(results),
            "mrr": sum(item[method]["mrr"] for item in results) / len(results),
        }

    Path(args.out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w", encoding="utf-8") as file:
        json.dump(
            {"summary": summary, "per_query": results},
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\n=== 检索评估汇总 ===")
    print(f"评估问题数：{len(results)}")
    print(f"精排设备：{device}")

    for method in methods:
        metrics = summary[method]
        print(
            f"{method:8} | "
            f"Hit@1: {metrics['hit_at_1']:.3f} | "
            f"Hit@3: {metrics['hit_at_3']:.3f} | "
            f"MRR: {metrics['mrr']:.3f}"
        )

    print(f"\n详细结果：{Path(args.out_path).resolve()}")


if __name__ == "__main__":
    main()