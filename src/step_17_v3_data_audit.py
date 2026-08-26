"""V3：审计训练、压力测试和严格验证数据的结构与标签分布。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "v3_legacy"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "v3_data_audit.json"

MODEL_COLUMNS = [
    "claimed_amount",
    "registry_amount",
    "issued_credits",
    "retired_credits",
    "discrepancy_ratio",
    "status_risk",
    "registry",
    "project_type",
    "country",
    "registry_status",
    "claim_context",
    "claim_tone",
]

DATASETS = {
    "synthetic_training": DATA_DIR / "noisy_synthetic_training_8000.csv",
    "generated_stress_test": (
        DATA_DIR / "registry_grounded_generated_line_item_cases_300.csv"
    ),
    "strict_real_validation": (
        DATA_DIR / "real_strict_cases_from_previous_project.csv"
    ),
}


def file_sha256(file_path: Path) -> str:
    """计算文件哈希，确保后续实验能够追溯到同一份原始数据。"""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def audit_dataset(name: str, file_path: Path) -> dict:
    """读取一个 CSV，并检查字段、标签和模型输入的缺失情况。"""
    if not file_path.is_file():
        raise FileNotFoundError(f"缺少数据文件：{file_path}")

    frame = pd.read_csv(file_path)

    missing_columns = [
        column
        for column in MODEL_COLUMNS + ["label"]
        if column not in frame.columns
    ]

    available_model_columns = [
        column
        for column in MODEL_COLUMNS
        if column in frame.columns
    ]

    missing_values = {
        column: int(frame[column].isna().sum())
        for column in available_model_columns
    }

    label_distribution = {}
    if "label" in frame.columns:
        label_distribution = {
            str(label): int(count)
            for label, count in frame["label"].value_counts(dropna=False)
            .sort_index()
            .items()
        }

    return {
        "dataset": name,
        "file_name": file_path.name,
        "sha256": file_sha256(file_path),
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": frame.columns.tolist(),
        "missing_required_columns": missing_columns,
        "label_distribution": label_distribution,
        "missing_values_in_model_columns": missing_values,
    }


def main() -> None:
    """审计三份 V3 数据，并输出可追溯 JSON 报告。"""
    results = {
        name: audit_dataset(name, file_path)
        for name, file_path in DATASETS.items()
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== V3 数据审计 ===")
    for name, result in results.items():
        print(f"\n数据集：{name}")
        print(f"行数：{result['row_count']}")
        print(f"标签分布：{result['label_distribution']}")
        print(f"缺失字段：{result['missing_required_columns']}")
        print(f"模型字段缺失值：{result['missing_values_in_model_columns']}")

    print(f"\n审计报告：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()