import argparse

from step_08_bm25_retriever import search as bm25_search
from step_07_dense_retriever import search as dense_search


# RRF 的平滑常数。60 是常用默认值。
RRF_K = 60


def hybrid_search(
    query: str,
    top_k: int = 5,
    candidate_k: int = 20,
    language: str | None = None,
    document_type: str | None = None,
    authority_level: str | None = None,
) -> list[dict]:
    """融合 Dense Retriever 与 BM25 Retriever 的候选结果。"""
    dense_results = dense_search(
        query=query,
        top_k=candidate_k,
        language=language,
        document_type=document_type,
        authority_level=authority_level,
    )

    bm25_results = bm25_search(
        query=query,
        top_k=candidate_k,
        language=language,
        document_type=document_type,
        authority_level=authority_level,
    )

    fused = {}

    # RRF 只关心名次：rank 越靠前，贡献越大。
    for source_name, results in {
        "dense": dense_results,
        "bm25": bm25_results,
    }.items():
        for rank, (chunk, _) in enumerate(results, start=1):
            chunk_id = chunk["chunk_id"]

            if chunk_id not in fused:
                fused[chunk_id] = {
                    "chunk": chunk,
                    "rrf_score": 0.0,
                    "dense_rank": None,
                    "bm25_rank": None,
                }

            fused[chunk_id]["rrf_score"] += 1 / (RRF_K + rank)
            fused[chunk_id][f"{source_name}_rank"] = rank

    ranked_results = sorted(
        fused.values(),
        key=lambda item: item["rrf_score"],
        reverse=True,
    )

    return ranked_results[:top_k]


def main() -> None:
    """提供命令行入口，方便比较混合检索结果。"""
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

    results = hybrid_search(
        query=args.query,
        top_k=args.top_k,
        candidate_k=args.candidate_k,
        language=args.language,
        document_type=args.document_type,
        authority_level=args.authority_level,
    )

    print(f"\n查询：{args.query}")
    print(f"融合候选数：{args.candidate_k}")
    print(f"返回结果数：{len(results)}")

    for rank, result in enumerate(results, start=1):
        chunk = result["chunk"]

        print(f"\n--- Top {rank} | RRF 分数：{result['rrf_score']:.6f} ---")
        print(
            f"Dense 排名：{result['dense_rank']} | "
            f"BM25 排名：{result['bm25_rank']}"
        )
        print(
            f"来源：{chunk['source_file']} | "
            f"第 {chunk['page_number']} 页 | "
            f"{chunk['language']} | {chunk['document_type']}"
        )
        print(f"文本：{chunk['text'][:220]}")


if __name__ == "__main__":
    main()
