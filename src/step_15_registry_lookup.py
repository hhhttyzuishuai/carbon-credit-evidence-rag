import argparse
import json
from functools import lru_cache
from pathlib import Path


# 自动定位项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 读取上一步标准化后的登记记录。
REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "registry_projects.jsonl"
)


def normalize_project_id(project_id: str) -> str:
    """统一项目 ID 的大小写与首尾空格，但不模糊匹配。"""
    return project_id.strip().upper()


@lru_cache(maxsize=1)
def load_project_index() -> dict[str, dict]:
    """读取 JSONL，并构建 Project ID 到记录的精确索引。"""
    project_index = {}

    with REGISTRY_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            project_id = normalize_project_id(record["project_id"])

            if project_id in project_index:
                raise ValueError(f"发现重复 Project ID：{project_id}")

            project_index[project_id] = record

    return project_index


def lookup_project(project_id: str) -> dict | None:
    """按 Project ID 精确查询；未找到时返回 None，不猜测相近项目。"""
    normalized_id = normalize_project_id(project_id)
    return load_project_index().get(normalized_id)


def format_number(value: int | float | None) -> str:
    """将信用数量显示为易读格式，同时保留空值。"""
    if value is None:
        return "未披露"

    return f"{value:,}"


def main() -> None:
    """命令行入口：根据项目 ID 精确返回登记记录字段。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()

    record = lookup_project(args.project_id)

    if record is None:
        print(f"未找到 Project ID：{args.project_id}")
        print("这不代表项目不存在；请核对项目 ID、数据版本或登记机构。")
        return

    print("\n=== 登记记录精确核对 ===")
    print(f"Project ID：{record['project_id']}")
    print(f"项目名称：{record['project_name']}")
    print(f"登记机构：{record['registry']}")
    print(f"项目状态：{record['voluntary_status']}")
    print(f"项目类型：{record['project_type']}")
    print(f"减排/移除：{record['reduction_or_removal']}")
    print(f"国家/地区：{record['country']} / {record['state']}")
    print(f"项目开发方：{record['project_developer']}")
    print(f"首次 Vintage 年份：{record['first_vintage_year']}")
    print(f"已签发数量：{format_number(record['total_credits_issued'])}")
    print(f"已注销数量：{format_number(record['total_credits_retired'])}")
    print(f"剩余数量：{format_number(record['total_credits_remaining'])}")

    print("\n=== 结构化数据来源 ===")
    print(f"工作簿：{record['source_workbook']}")
    print(f"工作表：{record['source_sheet']}")
    print(f"Excel 行号：{record['source_excel_row']}")


if __name__ == "__main__":
    main()