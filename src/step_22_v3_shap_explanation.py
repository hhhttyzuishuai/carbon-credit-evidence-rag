"""V3：使用 XGBoost 原生 TreeSHAP 贡献值输出全局和局部解释。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost

from step_18_train_v3_risk_model import (
    OUTPUTS_DIR,
    load_dataset,
    prepare_features,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "v3_calibrated_structured_audit_xgboost.joblib"

GLOBAL_OUTPUT_PATH = OUTPUTS_DIR / "v3_shap_global_importance.csv"
LOCAL_OUTPUT_PATH = OUTPUTS_DIR / "v3_shap_local_explanation.json"


def to_dense(matrix) -> np.ndarray:
    """将稀疏特征矩阵转换为 XGBoost 可解释的二维数组。"""
    if hasattr(matrix, "toarray"):
        return matrix.toarray()

    return np.asarray(matrix)


def get_feature_names(preprocessor) -> list[str]:
    """读取数值处理和 One-Hot 编码后的特征名。"""
    return [
        str(feature_name)
        for feature_name in preprocessor.get_feature_names_out()
    ]


def get_tree_shap_contributions(
    classifier,
    matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """调用 XGBoost 原生 pred_contribs，返回特征贡献与基准项。"""
    booster = classifier.get_booster()
    dmatrix = xgboost.DMatrix(matrix)

    contributions = np.asarray(
        booster.predict(dmatrix, pred_contribs=True)
    )

    # 二分类通常是：(样本数, 特征数 + 1)。
    # 若返回三维数组，则取正类对应的贡献。
    if contributions.ndim == 3 and contributions.shape[1] == 2:
        contributions = contributions[:, 1, :]

    if contributions.ndim != 2:
        raise ValueError(
            f"无法识别 XGBoost TreeSHAP 输出形状：{contributions.shape}"
        )

    # 最后一列是模型基准项，不属于输入特征贡献。
    return contributions[:, :-1], contributions[:, -1]


def json_value(value):
    """将 Pandas 和 NumPy 标量转换为 JSON 可写入类型。"""
    if pd.isna(value):
        return None

    if isinstance(value, np.generic):
        return value.item()

    return value


def main() -> None:
    """生成全局特征重要性与单条案例的局部 TreeSHAP 解释。"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        choices=[
            "synthetic_training",
            "generated_stress_test",
            "strict_real_validation",
        ],
        default="strict_real_validation",
    )
    parser.add_argument("--row-index", type=int, default=0)
    parser.add_argument("--background-size", type=int, default=200)
    parser.add_argument("--random-state", type=int, default=72443)
    args = parser.parse_args()

    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"未找到校准后的 V3 模型：{MODEL_PATH}")

    model = joblib.load(MODEL_PATH)
    preprocessor = model.named_steps["features"]
    classifier = model.named_steps["classifier"]
    feature_names = get_feature_names(preprocessor)

    # 全局解释使用固定随机抽样的训练数据，不使用严格真实验证集调参。
    global_frame = load_dataset("synthetic_training").sample(
        n=min(args.background_size, 8000),
        random_state=args.random_state,
    )

    global_matrix = to_dense(
        preprocessor.transform(prepare_features(global_frame))
    )
    global_contributions, _ = get_tree_shap_contributions(
        classifier,
        global_matrix,
    )

    if global_contributions.shape[1] != len(feature_names):
        raise ValueError("TreeSHAP 特征数与预处理特征名数量不一致。")

    global_importance = pd.DataFrame(
        {
            "feature": feature_names,
            "mean_absolute_tree_shap": np.abs(global_contributions).mean(axis=0),
        }
    ).sort_values("mean_absolute_tree_shap", ascending=False)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    global_importance.to_csv(GLOBAL_OUTPUT_PATH, index=False)

    local_frame = load_dataset(args.dataset)
    if args.row_index < 0 or args.row_index >= len(local_frame):
        raise IndexError(
            f"row-index 必须在 0 到 {len(local_frame) - 1} 之间。"
        )

    selected_row = local_frame.iloc[[args.row_index]]
    local_features = prepare_features(selected_row)
    local_matrix = to_dense(preprocessor.transform(local_features))

    local_contributions, base_values = get_tree_shap_contributions(
        classifier,
        local_matrix,
    )

    local_explanation = pd.DataFrame(
        {
            "feature": feature_names,
            "transformed_value": local_matrix[0],
            "tree_shap_value": local_contributions[0],
            "absolute_tree_shap_value": np.abs(local_contributions[0]),
        }
    ).sort_values("absolute_tree_shap_value", ascending=False)

    active_local_explanation = local_explanation[
        local_explanation["feature"].str.startswith("numeric__")
        | (local_explanation["transformed_value"] > 0.5)
    ].copy()

    probability = float(model.predict_proba(local_features)[0, 1])

    identity_columns = [
        column
        for column in ["case_id", "project_id", "label"]
        if column in selected_row.columns
    ]

    local_payload = {
        "dataset": args.dataset,
        "row_index": args.row_index,
        "case_identity": {
            column: json_value(selected_row.iloc[0][column])
            for column in identity_columns
        },
        "experimental_high_risk_probability": probability,
        "tree_shap_base_value_log_odds": float(base_values[0]),
        "important_note": (
            "TreeSHAP 解释的是模型分数的特征贡献，不构成因果关系、"
            "绿洗认定、违法认定或合规结论。"
        ),
        "top_feature_contributions": [
            {
                "feature": row["feature"],
                "transformed_value": float(row["transformed_value"]),
                "tree_shap_value": float(row["tree_shap_value"]),
            }
            for _, row in active_local_explanation.head(15).iterrows()
        ],
    }

    LOCAL_OUTPUT_PATH.write_text(
        json.dumps(local_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== V3 XGBoost TreeSHAP 解释完成 ===")
    print(f"解释模型：{MODEL_PATH.name}")
    print(f"局部案例：{local_payload['case_identity']}")
    print(f"实验性高风险概率：{probability:.4f}")
    print(f"全局重要性：{GLOBAL_OUTPUT_PATH}")
    print(f"局部解释：{LOCAL_OUTPUT_PATH}")

    print("\n局部贡献最大的前 10 个特征：")
    for _, row in active_local_explanation.head(10).iterrows():
        print(
            f"  {row['feature']}"
            f" | TreeSHAP={row['tree_shap_value']:.6f}"
            f" | 特征值={row['transformed_value']:.4f}"
        )


if __name__ == "__main__":
    main()