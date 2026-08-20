import hashlib
import json
import re
from collections import Counter
from pathlib import Path


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 输入：已包含中英文元数据的逐页文本。
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_pages.jsonl"

# 输出：后续检索使用的 Chunk 文件。
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_chunks.jsonl"

# 英文按单词切分的参数。
EN_CHUNK_SIZE = 180
EN_OVERLAP = 40

# 中文按字符和句子切分的参数。
ZH_CHUNK_SIZE = 380
ZH_OVERLAP = 80
# 过短内容通常是封面、页眉或句子碎片，不参与检索。
MIN_ZH_CHARS = 40
MIN_EN_WORDS = 12


def make_source_key(source_path: str) -> str:
    """根据来源路径生成稳定且不会重复的文档标识。"""
    readable_part = re.sub(r"[^a-z0-9]+", "_", source_path.lower()).strip("_")

    # 中文文件名没有英文字母时，使用通用名称，避免生成空 ID。
    if not readable_part:
        readable_part = "document"

    # 哈希保证不同路径的文件不会产生相同 ID。
    short_hash = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:8]

    return f"{readable_part[:50]}_{short_hash}"


def split_english_text(text: str) -> list[str]:
    """按英文单词切分，并保留相邻 Chunk 的重叠内容。"""
    words = text.split()

    if not words:
        return []

    chunks = []
    step = EN_CHUNK_SIZE - EN_OVERLAP

    for start in range(0, len(words), step):
        chunk_words = words[start : start + EN_CHUNK_SIZE]

        if not chunk_words:
            break

        chunks.append(" ".join(chunk_words))

        if start + EN_CHUNK_SIZE >= len(words):
            break

    return chunks


def keep_chinese_overlap(sentences: list[str]) -> list[str]:
    """保留末尾约 80 个字符对应的完整句子，作为下一 Chunk 的上下文。"""
    overlap_sentences = []
    overlap_length = 0

    for sentence in reversed(sentences):
        if overlap_length + len(sentence) > ZH_OVERLAP:
            break

        overlap_sentences.insert(0, sentence)
        overlap_length += len(sentence)

    return overlap_sentences


def split_chinese_text(text: str) -> list[str]:
    """优先按中文句末标点切分，过长时才按字符强制拆分。"""
    sentences = re.split(r"(?<=[。！？；])", text)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]

    chunks = []
    current_sentences = []
    current_length = 0

    for sentence in sentences:
        # 极长单句无法按标点继续拆分，只能按字符窗口切分。
        if len(sentence) > ZH_CHUNK_SIZE:
            if current_sentences:
                chunks.append("".join(current_sentences))
                current_sentences = []
                current_length = 0

            step = ZH_CHUNK_SIZE - ZH_OVERLAP

            for start in range(0, len(sentence), step):
                piece = sentence[start : start + ZH_CHUNK_SIZE]

                if not piece:
                    break

                chunks.append(piece)

                if start + ZH_CHUNK_SIZE >= len(sentence):
                    break

            continue

        # 当前 Chunk 加入新句子后超长，先写入已有内容。
        if current_sentences and current_length + len(sentence) > ZH_CHUNK_SIZE:
            chunks.append("".join(current_sentences))

            # 下一块保留上一块的末尾句子，避免上下文断裂。
            current_sentences = keep_chinese_overlap(current_sentences)
            current_length = sum(len(item) for item in current_sentences)

        current_sentences.append(sentence)
        current_length += len(sentence)

    if current_sentences:
        chunks.append("".join(current_sentences))

    return chunks


def split_text(text: str, language: str) -> list[str]:
    """按语料语言选择合适的 Chunk 切分策略。"""
    if language == "zh":
        return split_chinese_text(text)

    return split_english_text(text)
def should_keep_for_retrieval(text: str, language: str) -> bool:
    """判断 Chunk 是否有足够内容进入检索语料。"""
    if language == "zh":
        return len(text) >= MIN_ZH_CHARS

    return len(text.split()) >= MIN_EN_WORDS


def main() -> None:
    """读取逐页文本，生成带完整来源元数据的中英文 Chunk。"""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"找不到输入文件：{INPUT_PATH}")

    total_pages = 0
    total_chunks = 0
    skipped_short_chunks = 0
    chunk_counts = Counter()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with (
        INPUT_PATH.open("r", encoding="utf-8") as input_file,
        OUTPUT_PATH.open("w", encoding="utf-8") as output_file,
    ):
        for line in input_file:
            page_record = json.loads(line)

            source_path = page_record["source_path"]
            source_key = make_source_key(source_path)
            language = page_record["language"]

            page_chunks = split_text(
                text=page_record["text"],
                language=language,
            )

            kept_chunk_index = 0

            for chunk_text in page_chunks:
                # 封面、页眉和碎片文本不写入检索语料。
                if not should_keep_for_retrieval(chunk_text, language):
                    skipped_short_chunks += 1
                    continue

                # 编号只针对保留下来的 Chunk 连续递增。
                kept_chunk_index += 1

                chunk_record = {
                    "chunk_id": (
                        f"{source_key}-p{page_record['page_number']}"
                        f"-c{kept_chunk_index}"
                    ),
                    "source_file": page_record["source_file"],
                    "source_path": source_path,
                    "page_number": page_record["page_number"],
                    "chunk_index": kept_chunk_index,
                    "language": language,
                    "document_type": page_record["document_type"],
                    "authority_level": page_record["authority_level"],
                    "char_count": len(chunk_text),
                    "word_count": (
                        len(chunk_text.split()) if language == "en" else None
                    ),
                    "text": chunk_text,
                }

                output_file.write(
                    json.dumps(chunk_record, ensure_ascii=False) + "\n"
                )

                total_chunks += 1
                chunk_counts[language] += 1

            total_pages += 1

    print(f"处理页数：{total_pages}")
    print(f"中文 Chunk 数：{chunk_counts['zh']}")
    print(f"英文 Chunk 数：{chunk_counts['en']}")
    print(f"过滤的过短 Chunk 数：{skipped_short_chunks}")
    print(f"总 Chunk 数：{total_chunks}")
    print(f"Chunk 文件：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()