# from pathlib import Path
#
# from pypdf import PdfReader
#
#
# # 自动定位项目根目录，避免因 PyCharm 运行位置不同而找不到资料文件。
# PROJECT_ROOT = Path(__file__).resolve().parents[1]
#
#
# def extract_pages(pdf_path: Path) -> list[dict]:
#     """逐页提取 PDF 文本，并保留来源文件名与页码。"""
#     reader = PdfReader(pdf_path)
#     page_records = []
#
#     # enumerate(..., start=1) 让页码从人类习惯的第 1 页开始。
#     for page_number, page in enumerate(reader.pages, start=1):
#         raw_text = page.extract_text() or ""
#
#         # 合并多余换行和空格，让后续切块、检索更稳定。
#         clean_text = " ".join(raw_text.split())
#
#         # 空白页不进入后续 RAG 语料。
#         if not clean_text:
#             continue
#
#         page_records.append(
#             {
#                 "source_file": pdf_path.name,
#                 "page_number": page_number,
#                 "text": clean_text,
#             }
#         )
#
#     return page_records
#
#
# if __name__ == "__main__":
#     # 先用 Woodside 报告作为样例，验证“PDF → 带页码文本”的最小流程。
#     sample_pdf = PROJECT_ROOT / "data" / "raw" / "disclosures" / "2.Woodside Energy.pdf"
#
#     records = extract_pages(sample_pdf)
#
#     print(f"文件：{sample_pdf.name}")
#     print(f"成功提取的非空页数：{len(records)}")
#     print("\n第 1 页文本预览：")
#     print(records[0]["text"][:500])

import json
from pathlib import Path

from pypdf import PdfReader


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 原始 PDF 的存放目录。
RAW_PDF_DIR = PROJECT_ROOT / "data" / "raw" / "disclosures"

# 提取后的逐页文本存放位置。
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_pages.jsonl"


def extract_pages(pdf_path: Path) -> list[dict]:
    """逐页提取 PDF 文本，并保留可追溯的来源信息。"""
    reader = PdfReader(pdf_path)
    page_records = []

    for page_number, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        clean_text = " ".join(raw_text.split())

        # 空白页不写入后续语料。
        if not clean_text:
            continue

        page_records.append(
            {
                "source_file": pdf_path.name,
                "source_path": str(pdf_path.relative_to(PROJECT_ROOT)),
                "page_number": page_number,
                "text": clean_text,
            }
        )

    return page_records


def save_as_jsonl(records: list[dict], output_path: Path) -> None:
    """每行写入一页记录，形成 JSONL 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    all_records = []

    # 遍历资料目录下的全部 PDF。
    for pdf_path in sorted(RAW_PDF_DIR.glob("*.pdf")):
        page_records = extract_pages(pdf_path)
        all_records.extend(page_records)
        print(f"{pdf_path.name}：提取 {len(page_records)} 页")

    save_as_jsonl(all_records, OUTPUT_PATH)

    print(f"\n总计写入 {len(all_records)} 条逐页记录")
    print(f"输出文件：{OUTPUT_PATH}")