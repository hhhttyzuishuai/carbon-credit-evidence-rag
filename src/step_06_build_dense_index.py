import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 输入：通过质量检查的中英文 Chunk。
CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_chunks.jsonl"

# 输出：本地向量索引目录。
INDEX_DIR = PROJECT_ROOT / "data" / "index"

# 使用与冒烟测试相同的中英文 Embedding 模型。
MODEL_NAME = "intfloat/multilingual-e5-small"

# RTX 3050 Ti 显存为 4GB，先采用保守批次大小。
BATCH_SIZE = 16

# 有 CUDA 时使用 GPU，否则自动回退 CPU。
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_chunks(chunks_path: Path) -> list[dict]:
    """逐行读取 JSONL 中的全部 Chunk。"""
    with chunks_path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def file_sha256(file_path: Path) -> str:
    """计算 Chunk 文件哈希，用于确认索引与源数据是否匹配。"""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def main() -> None:
    """将全部 Chunk 编码为归一化向量，并保存索引和映射关系。"""
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"找不到 Chunk 文件：{CHUNKS_PATH}")

    chunks = load_chunks(CHUNKS_PATH)

    # E5 约定：被检索的资料文本必须使用 passage: 前缀。
    passages = [f"passage: {chunk['text']}" for chunk in chunks]

    print(f"待编码 Chunk 数：{len(chunks)}")
    print(f"Embedding 模型：{MODEL_NAME}")
    print(f"运行设备：{DEVICE}")
    print(f"批次大小：{BATCH_SIZE}")

    model = SentenceTransformer(MODEL_NAME, device=DEVICE)

    # normalize_embeddings=True 后，向量点积等价于余弦相似度。
    embeddings = model.encode(
        passages,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    ).astype(np.float32)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # 保存向量矩阵：第 i 行对应 chunk_ids.json 中第 i 个 Chunk ID。
    np.save(INDEX_DIR / "embeddings.npy", embeddings)

    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    (INDEX_DIR / "chunk_ids.json").write_text(
        json.dumps(chunk_ids, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 保存索引版本信息，未来可防止“资料已更新但索引未重建”的问题。
    manifest = {
        "model_name": MODEL_NAME,
        "device_used": DEVICE,
        "num_chunks": len(chunks),
        "embedding_dimension": int(embeddings.shape[1]),
        "chunk_source_sha256": file_sha256(CHUNKS_PATH),
    }

    (INDEX_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n向量矩阵形状：{embeddings.shape}")
    print(f"向量索引目录：{INDEX_DIR}")


if __name__ == "__main__":
    main()