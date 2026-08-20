import json
from pathlib import Path

from pypdf import PdfReader


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 扫描整个原始资料目录，而不只扫描英文 disclosures 文件夹。
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

# 所有 PDF 的逐页文本会重新写入这里。
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "pdf_pages.jsonl"


def classify_document(pdf_path: Path) -> dict:
    """根据文件所在目录和文件名，补充检索时需要的元数据。"""
    relative_path = pdf_path.relative_to(PROJECT_ROOT)
    path_parts = relative_path.parts

    # chinese 目录下的文件视为中文，其余当前资料为英文。
    language = "zh" if "chinese" in path_parts else "en"

    # Anew 是企业评论信，不应被误认为企业可持续发展报告。
    if pdf_path.name == "1.Anew Carbon Development, LLC.pdf":
        return {
            "language": language,
            "document_type": "comment_letter",
            "authority_level": "company_opinion",
        }

    # 中文官方规则文件。
    if "policies" in path_parts:
        return {
            "language": language,
            "document_type": "official_rule",
            "authority_level": "official",
        }

    # 中文官方市场发展报告。
    if "reports" in path_parts:
        return {
            "language": language,
            "document_type": "official_market_report",
            "authority_level": "official",
        }

    # 其余 PDF 均为企业公开披露材料。
    return {
        "language": language,
        "document_type": "company_disclosure",
        "authority_level": "company_disclosure",
    }


def extract_pages(pdf_path: Path) -> list[dict]:
    """逐页提取 PDF 文本，并保留来源、页码和分类元数据。"""
    reader = PdfReader(pdf_path)
    page_records = []

    metadata = classify_document(pdf_path)

    for page_number, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        clean_text = " ".join(raw_text.split())

        # 空白页不进入后续 RAG 语料。
        if not clean_text:
            continue

        page_records.append(
            {
                "source_file": pdf_path.name,
                # 使用 /，让 JSON 在 Windows、Linux、Docker 中都更一致。
                "source_path": pdf_path.relative_to(PROJECT_ROOT).as_posix(),
                "page_number": page_number,
                "text": clean_text,
                **metadata,
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

    # rglob 会递归查找 raw 目录中的全部 PDF。
    pdf_files = sorted(RAW_DATA_DIR.rglob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(f"未在目录中找到 PDF：{RAW_DATA_DIR}")

    for pdf_path in pdf_files:
        page_records = extract_pages(pdf_path)
        all_records.extend(page_records)

        metadata = classify_document(pdf_path)
        relative_path = pdf_path.relative_to(PROJECT_ROOT).as_posix()

        print(
            f"{relative_path}：{len(page_records)} 页，"
            f"{metadata['language']}，{metadata['document_type']}"
        )

    # 只覆盖程序生成的中间文件，不会覆盖任何原始 PDF 或 Excel。
    save_as_jsonl(all_records, OUTPUT_PATH)

    print(f"\n找到 PDF 文件数：{len(pdf_files)}")
    print(f"总计写入逐页记录：{len(all_records)}")
    print(f"输出文件：{OUTPUT_PATH}")