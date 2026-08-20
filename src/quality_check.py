import json
from collections import defaultdict
from pathlib import Path


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 上一步生成的逐页文本数据。
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_pages.jsonl"

# 本次检查报告的输出位置。
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_quality_report.json"

# 这些字符常见于 PDF 文本提取时的编码异常。
SUSPICIOUS_CHARACTERS = ("�", "鈥")


def has_suspicious_encoding(text: str) -> bool:
    """判断文本中是否包含疑似乱码字符。"""
    return any(character in text for character in SUSPICIOUS_CHARACTERS)


def main() -> None:
    """读取逐页文本，按文件统计页数、文本长度和疑似乱码页。"""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"找不到输入文件：{INPUT_PATH}")

    # defaultdict 自动为每份文件创建初始统计结构。
    stats = defaultdict(
        lambda: {
            "page_count": 0,
            "text_char_count": 0,
            "suspicious_pages": [],
        }
    )

    total_records = 0

    # JSONL 适合逐行读取，不需要一次性把全部数据放进内存。
    with INPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)

            source_file = record["source_file"]
            page_number = record["page_number"]
            text = record["text"]

            stats[source_file]["page_count"] += 1
            stats[source_file]["text_char_count"] += len(text)

            if has_suspicious_encoding(text):
                stats[source_file]["suspicious_pages"].append(page_number)

            total_records += 1

    # 转成普通字典，便于写入 JSON 文件。
    report = {
        "total_page_records": total_records,
        "files": dict(stats),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"检查记录总数：{total_records}")
    print("\n=== 各文件质量概览 ===")

    for source_file, info in report["files"].items():
        print(f"\n文件：{source_file}")
        print(f"  提取页数：{info['page_count']}")
        print(f"  文本字符数：{info['text_char_count']}")
        print(f"  疑似乱码页：{info['suspicious_pages'] or '无'}")

    print(f"\n质量报告已写入：{REPORT_PATH}")


if __name__ == "__main__":
    main()