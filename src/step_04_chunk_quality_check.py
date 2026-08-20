import json
from collections import Counter
from pathlib import Path


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 检查最新生成的 Chunk 文件。
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_chunks.jsonl"

# 中文少于 40 字的 Chunk 通常只有封面标题或页眉页脚。
MIN_ZH_CHARS = 40

# 英文少于 12 个单词的 Chunk 通常缺少足够语义。
MIN_EN_WORDS = 12

# 每条 Chunk 必须具备的可追溯字段。
REQUIRED_FIELDS = {
    "chunk_id",
    "source_file",
    "source_path",
    "page_number",
    "language",
    "document_type",
    "authority_level",
    "text",
}


def is_short_chunk(record: dict) -> bool:
    """按语言判断 Chunk 是否短到不适合参与检索。"""
    if record["language"] == "zh":
        return record["char_count"] < MIN_ZH_CHARS

    return record["word_count"] < MIN_EN_WORDS


def main() -> None:
    """检查 Chunk 的完整性、重复 ID 和过短文本。"""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"找不到 Chunk 文件：{INPUT_PATH}")

    total_chunks = 0
    language_counts = Counter()
    short_counts = Counter()
    seen_ids = set()
    duplicate_ids = []
    missing_field_records = []
    short_samples = []

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            total_chunks += 1

            language = record["language"]
            language_counts[language] += 1

            # 检查 ID 是否重复。
            if record["chunk_id"] in seen_ids:
                duplicate_ids.append(record["chunk_id"])
            seen_ids.add(record["chunk_id"])

            # 检查关键元数据字段是否缺失。
            missing_fields = REQUIRED_FIELDS - set(record.keys())
            if missing_fields:
                missing_field_records.append(
                    {
                        "chunk_id": record.get("chunk_id", "未知"),
                        "missing_fields": sorted(missing_fields),
                    }
                )

            # 统计过短 Chunk，并保存少量样例用于人工确认。
            if is_short_chunk(record):
                short_counts[language] += 1

                if len(short_samples) < 5:
                    short_samples.append(
                        {
                            "chunk_id": record["chunk_id"],
                            "language": language,
                            "source_file": record["source_file"],
                            "page_number": record["page_number"],
                            "text": record["text"][:80],
                        }
                    )

    print(f"Chunk 总数：{total_chunks}")
    print(f"中文 Chunk 数：{language_counts['zh']}")
    print(f"英文 Chunk 数：{language_counts['en']}")
    print(f"重复 Chunk ID 数：{len(duplicate_ids)}")
    print(f"缺失关键字段的记录数：{len(missing_field_records)}")
    print(f"过短中文 Chunk 数：{short_counts['zh']}")
    print(f"过短英文 Chunk 数：{short_counts['en']}")

    print("\n=== 过短 Chunk 样例 ===")
    for sample in short_samples:
        print(
            f"\n{sample['language']} | {sample['source_file']} "
            f"| 第 {sample['page_number']} 页"
        )
        print(sample["text"])


if __name__ == "__main__":
    main()