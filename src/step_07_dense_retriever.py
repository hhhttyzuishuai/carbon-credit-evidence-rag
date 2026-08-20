import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 预处理后的 Chunk 文件。
CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_chunks.jsonl"

# 本地向量索引目录。
INDEX_DIR = PROJECT_ROOT / "data" / "index"

# 与建索引时必须完全相同的 Embedding 模型。
MODEL_NAME = "intfloat/multilingual-e5-small"

# 查询编码使用 GPU；无 GPU 时自动回退 CPU。
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def file_sha256(file_path: Path) -> str:
    """计算文件哈希，用于确认索引没有过期。"""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def load_chunks() -> list[dict]:
    """读取全部 Chunk，并保持与建索引时相同的顺序。"""
    with CHUNKS_PATH.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def load_index() -> tuple[list[dict], np.ndarray, dict]:
    """加载 Chunk、向量矩阵和索引清单，并检查它们是否匹配。"""
    chunks = load_chunks()

    embeddings = np.load(INDEX_DIR / "embeddings.npy")

    chunk_ids = json.loads(
        (INDEX_DIR / "chunk_ids.json").read_text(encoding="utf-8")
    )

    manifest = json.loads(
        (INDEX_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    # 如果 Chunk 文件修改过但没有重建索引，必须停止，不能静默返回错误结果。
    if manifest["chunk_source_sha256"] != file_sha256(CHUNKS_PATH):
        raise ValueError(
            "Chunk 数据已变化，请先重新运行 step_06_build_dense_index.py"
        )

    current_ids = [chunk["chunk_id"] for chunk in chunks]

    if current_ids != chunk_ids:
        raise ValueError("Chunk ID 顺序与向量索引不一致，请重建索引")

    return chunks, embeddings, manifest


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


def search(
    query: str,
    top_k: int = 5,
    language: str | None = None,
    document_type: str | None = None,
    authority_level: str | None = None,
) -> list[tuple[dict, float]]:
    """将查询编码为向量，并返回余弦相似度最高的 Chunk。"""
    chunks, embeddings, _ = load_index()

    # E5 约定：用户问题必须加 query: 前缀。
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)

    query_embedding = model.encode(
        [f"query: {query}"],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0]

    # 向量已归一化，因此点积等于余弦相似度。
    scores = embeddings @ query_embedding

    candidate_indices = [
        index
        for index, chunk in enumerate(chunks)
        if matches_filters(
            chunk,
            language=language,
            document_type=document_type,
            authority_level=authority_level,
        )
    ]

    ranked_indices = sorted(
        candidate_indices,
        key=lambda index: scores[index],
        reverse=True,
    )[:top_k]

    return [(chunks[index], float(scores[index])) for index in ranked_indices]


def main() -> None:
    """提供命令行检索入口，便于先人工检查召回结果。"""
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
    print(f"检索设备：{DEVICE}")
    print(f"返回结果数：{len(results)}")

    for rank, (chunk, score) in enumerate(results, start=1):
        preview = chunk["text"][:220]

        print(f"\n--- Top {rank} | 分数：{score:.4f} ---")
        print(
            f"来源：{chunk['source_file']} | "
            f"第 {chunk['page_number']} 页 | "
            f"{chunk['language']} | {chunk['document_type']}"
        )
        print(f"文本：{preview}")


if __name__ == "__main__":
    main()
