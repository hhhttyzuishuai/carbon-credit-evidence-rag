"""V3：在接入旧论文模型前，审计其类别、特征和运行环境。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import sklearn
import xgboost


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "v3_model_audit.json"


def file_sha256(file_path: Path) -> str:
    """计算模型文件哈希，记录本次审计针对的具体模型版本。"""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def to_json_value(value):
    """将 NumPy、路径和其他对象转换为可写入 JSON 的普通 Python 类型。"""
    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"

    if isinstance(value, dict):
        return {
            str(key): to_json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def audit_model(model_path: Path) -> dict:
    """只读加载可信的本地模型，提取可解释的元信息。"""
    model = joblib.load(model_path)

    classes = getattr(model, "classes_", None)
    feature_names = getattr(model, "feature_names_in_", None)
    feature_count = getattr(model, "n_features_in_", None)

    booster_info = {}
    if hasattr(model, "get_booster"):
        booster = model.get_booster()
        booster_info = {
            "feature_names": booster.feature_names,
            "feature_types": booster.feature_types,
            "config": json.loads(booster.save_config()),
        }

    parameters = {}
    if hasattr(model, "get_params"):
        parameters = {
            key: to_json_value(value)
            for key, value in model.get_params().items()
        }

    return {
        "model_path": str(model_path.resolve()),
        "model_file_name": model_path.name,
        "model_sha256": file_sha256(model_path),
        "model_class": f"{type(model).__module__}.{type(model).__name__}",
        "xgboost_runtime_version": xgboost.__version__,
        "scikit_learn_runtime_version": sklearn.__version__,
        "classes": to_json_value(classes) if classes is not None else None,
        "n_features_in": int(feature_count) if feature_count is not None else None,
        "feature_names_in": (
            to_json_value(feature_names)
            if feature_names is not None
            else None
        ),
        "model_parameters": parameters,
        "booster": booster_info,
    }


def main() -> None:
    """命令行入口：审计指定的本地 XGBoost joblib 模型。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"未找到模型文件：{args.model}")

    audit_result = audit_model(args.model)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            audit_result,
            ensure_ascii=False,
            indent=2,
            default=to_json_value,
        ),
        encoding="utf-8",
    )

    print("=== V3 模型审计 ===")
    print(f"模型：{audit_result['model_file_name']}")
    print(f"模型类型：{audit_result['model_class']}")
    print(f"模型类别：{audit_result['classes']}")
    print(f"输入特征数：{audit_result['n_features_in']}")
    print(f"特征名：{audit_result['feature_names_in']}")
    print(f"当前 XGBoost：{audit_result['xgboost_runtime_version']}")
    print(f"当前 Scikit-learn：{audit_result['scikit_learn_runtime_version']}")
    print(f"模型 SHA256：{audit_result['model_sha256']}")
    print(f"审计结果：{args.out.resolve()}")


if __name__ == "__main__":
    main()