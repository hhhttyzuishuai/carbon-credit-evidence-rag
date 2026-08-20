import json
import re
from pathlib import Path


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 输入：上一步提取的逐页 PDF 文本。
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_pages.jsonl"

# 输出：后续检索真正要使用的 Chunk 数据。
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_chunks.jsonl"

# 每个 Chunk 最多 180 个英文单词。
CHUNK_SIZE = 180

# 相邻 Chunk 重复保留 40 个单词，避免一句话刚好被切断后丢失上下文。
OVERLAP = 40


def make_source_key(source_file: str) -> str:
    """将文件名转成稳定、适合用作 ID 的短名称。"""
    file_stem = Path(source_file).stem.lower()
    return re.sub(r"[^a-z0-9]+", "_", file_stem).strip("_")


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """按单词切分文本，并让相邻 Chunk 保留部分重叠内容。"""
    if overlap >= chunk_size:
        raise ValueError("OVERLAP 必须小于 CHUNK_SIZE")

    words = text.split()

    if not words:
        return []

    chunks = []
    step = chunk_size - overlap

    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size]

        if not chunk_words:
            break

        chunks.append(" ".join(chunk_words))

        # 已经覆盖最后一个单词时停止，避免产生重复的尾部 Chunk。
        if start + chunk_size >= len(words):
            break

    return chunks


def main() -> None:
    """读取逐页记录，切分后写入带来源和页码的 Chunk 数据。"""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"找不到输入文件：{INPUT_PATH}")

    total_pages = 0
    total_chunks = 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with (
        INPUT_PATH.open("r", encoding="utf-8") as input_file,
        OUTPUT_PATH.open("w", encoding="utf-8") as output_file,
    ):
        for line in input_file:
            page_record = json.loads(line)

            source_file = page_record["source_file"]
            page_number = page_record["page_number"]
            source_key = make_source_key(source_file)

            page_chunks = split_text(
                text=page_record["text"],
                chunk_size=CHUNK_SIZE,
                overlap=OVERLAP,
            )

            for chunk_index, chunk_text in enumerate(page_chunks, start=1):
                chunk_record = {
                    # 稳定 ID：同一份资料重复运行后，编号不会随机变化。
                    "chunk_id": f"{source_key}-p{page_number}-c{chunk_index}",
                    "source_file": source_file,
                    "source_path": page_record["source_path"],
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "word_count": len(chunk_text.split()),
                    "text": chunk_text,
                }

                output_file.write(
                    json.dumps(chunk_record, ensure_ascii=False) + "\n"
                )
                total_chunks += 1

            total_pages += 1

    print(f"处理页数：{total_pages}")
    print(f"生成 Chunk 数：{total_chunks}")
    print(f"Chunk 文件：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()