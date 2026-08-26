import argparse
import json
from pathlib import Path

import pandas as pd


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 原始登记记录 Excel；只读，不修改。
DEFAULT_INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "registry"
    / "Dim_C_Voluntary-Registry-Offsets-Database--v2026-02.xlsx"
)

# V2 生成的结构化查询数据。
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "registry_projects.jsonl"
)

# PROJECTS 表前 3 行是说明信息；第 4 行才是字段名。
SHEET_NAME = "PROJECTS"
HEADER_ROW = 3

# V2 首版只保留可用于精确核对的核心字段。
REQUIRED_COLUMNS = [
    "Project ID",
    "Project Name",
    "Voluntary Registry",
    "Voluntary Status",
    "Scope",
    "Type",
    "Reduction / Removal",
    "Country",
    "State",
    "Project Developer",
    "Total Credits Issued",
    "Total Credits Retired",
    "Total Credits Remaining",
    "First Year of Project (Vintage)",
]


def normalize_column_name(column_name: object) -> str:
    """将 Excel 表头中的换行和连续空格统一为单个空格。"""
    return " ".join(str(column_name).split())


def clean_text(value: object) -> str | None:
    """将空值转为 None，其余值转为去除首尾空格的文本。"""
    if pd.isna(value):
        return None

    text = str(value).strip()
    return text or None


def clean_number(value: object) -> int | float | None:
    """保留数值类型，避免将碳信用数量写成文本。"""
    if pd.isna(value):
        return None

    number = float(value)
    return int(number) if number.is_integer() else number


def load_registry_projects(input_path: Path) -> list[dict]:
    """读取 PROJECTS 工作表，并生成字段统一的项目记录。"""
    dataframe = pd.read_excel(
        input_path,
        sheet_name=SHEET_NAME,
        header=HEADER_ROW,
    )

    # 统一 Excel 表头，解决换行造成的字段名不一致问题。
    dataframe.columns = [
        normalize_column_name(column)
        for column in dataframe.columns
    ]

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in dataframe.columns
    ]
    if missing_columns:
        raise ValueError(
            f"Excel 缺少 V2 所需字段：{missing_columns}"
        )

    # 只保留具有项目 ID 的真实项目行，跳过汇总或空白行。
    dataframe = dataframe[
        dataframe["Project ID"].notna()
    ].copy()

    dataframe["Project ID"] = (
        dataframe["Project ID"]
        .astype(str)
        .str.strip()
    )
    dataframe = dataframe[
        dataframe["Project ID"] != ""
    ].copy()

    duplicate_ids = dataframe[
        dataframe["Project ID"].duplicated()
    ]["Project ID"].tolist()
    if duplicate_ids:
        raise ValueError(
            f"发现重复 Project ID，例如：{duplicate_ids[:5]}"
        )

    records = []

    for dataframe_index, row in dataframe.iterrows():
        # dataframe 第 0 行对应 Excel 第 5 行：
        # 第 1-3 行为说明，第 4 行为表头。
        excel_row = int(dataframe_index) + HEADER_ROW + 2

        records.append(
            {
                "project_id": clean_text(row["Project ID"]),
                "project_name": clean_text(row["Project Name"]),
                "registry": clean_text(row["Voluntary Registry"]),
                "voluntary_status": clean_text(
                    row["Voluntary Status"]
                ),
                "scope": clean_text(row["Scope"]),
                "project_type": clean_text(row["Type"]),
                "reduction_or_removal": clean_text(
                    row["Reduction / Removal"]
                ),
                "country": clean_text(row["Country"]),
                "state": clean_text(row["State"]),
                "project_developer": clean_text(
                    row["Project Developer"]
                ),
                "total_credits_issued": clean_number(
                    row["Total Credits Issued"]
                ),
                "total_credits_retired": clean_number(
                    row["Total Credits Retired"]
                ),
                "total_credits_remaining": clean_number(
                    row["Total Credits Remaining"]
                ),
                "first_vintage_year": clean_number(
                    row["First Year of Project (Vintage)"]
                ),
                # 溯源信息：后续界面会展示它，而不是让模型编造数值来源。
                "source_workbook": input_path.name,
                "source_sheet": SHEET_NAME,
                "source_excel_row": excel_row,
            }
        )

    return records


def write_jsonl(records: list[dict], output_path: Path) -> None:
    """将标准化记录写入本地 JSONL，供 V2 精确查询模块使用。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )


def main() -> None:
    """命令行入口：Excel 登记记录 → 可查询 JSONL。"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
    )
    args = parser.parse_args()

    records = load_registry_projects(args.input)
    write_jsonl(records, args.out)

    print(f"读取工作表：{SHEET_NAME}")
    print(f"项目记录数：{len(records)}")
    print(f"输出文件：{args.out.resolve()}")

    if records:
        example = records[0]
        print("\n首条样例：")
        print(
            f"Project ID={example['project_id']} | "
            f"Registry={example['registry']} | "
            f"Status={example['voluntary_status']} | "
            f"Excel 行号={example['source_excel_row']}"
        )


if __name__ == "__main__":
    main()