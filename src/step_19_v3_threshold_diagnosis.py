"""V3：诊断严格真实验证集上的概率分布与默认阈值表现。"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

from step_18_train_v3_risk_model import (
    OUTPUTS_DIR,
    load_dataset,
    prepare_features,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "v3_structured_audit_xgboost.joblib"
PREDICTIONS_PATH = OUTPUTS_DIR / "v3_strict_threshold_diagnosis.csv"
SUMMARY_PATH = OUTPUTS_DIR / "v3_strict_threshold_diagnosis.json"


def threshold_metrics(
    labels: pd.Series,
    probabilities: pd.Series,
    threshold: float,
) -> dict:
    """计算指定阈值下的分类表现，仅用于诊断。"""
    predictions = (probabilities >= threshold).astype(int)

    return {
        "threshold": threshold,
        "predicted_high_risk_count": int(predictions.sum()),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
    }


def main() -> None:
    """导出严格真实验证集的概率与三个固定阈值的诊断结果。"""
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"未找到当前 V3 模型：{MODEL_PATH}")

    model = joblib.load(MODEL_PATH)
    frame = load_dataset("strict_real_validation")
    labels = frame["label"].astype(int)

    probabilities = pd.Series(
        model.predict_proba(prepare_features(frame))[:, 1],
        index=frame.index,
        name="high_risk_probability",
    )

    display_columns = [
        column
        for column in [
            "case_id",
            "project_id",
            "label",
            "claimed_amount",
            "registry_amount",
            "discrepancy_ratio",
            "status_risk",
        ]
        if column in frame.columns
    ]

    diagnosis = frame[display_columns].copy()
    diagnosis["missing_claimed_amount"] = frame["claimed_amount"].isna()
    diagnosis["high_risk_probability"] = probabilities
    diagnosis["prediction_at_0_50"] = (probabilities >= 0.50).astype(int)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    diagnosis.to_csv(PREDICTIONS_PATH, index=False)

    probability_by_label = {
        str(label): {
            "count": int(len(group)),
            "min": float(group.min()),
            "mean": float(group.mean()),
            "max": float(group.max()),
        }
        for label, group in probabilities.groupby(labels)
    }

    summary = {
        "dataset": "strict_real_validation",
        "cases": int(len(frame)),
        "label_distribution": {
            str(label): int(count)
            for label, count in labels.value_counts().sort_index().items()
        },
        "probability_by_true_label": probability_by_label,
        "fixed_threshold_diagnostics": [
            threshold_metrics(labels, probabilities, threshold)
            for threshold in [0.35, 0.50, 0.65]
        ],
        "important_note": (
            "本文件仅用于观察跨数据集概率分布，不应用严格真实验证集标签"
            "来选择最终部署阈值。"
        ),
    }

    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== V3 严格真实验证集阈值诊断 ===")
    print(f"案例数：{summary['cases']}")
    print(f"真实标签分布：{summary['label_distribution']}")
    print(f"按真实标签的概率范围：{probability_by_label}")

    for result in summary["fixed_threshold_diagnostics"]:
        print(
            f"\n阈值 {result['threshold']:.2f}"
            f" | 预测高风险：{result['predicted_high_risk_count']}"
            f" | Precision：{result['precision']:.3f}"
            f" | Recall：{result['recall']:.3f}"
            f" | F1：{result['f1']:.3f}"
        )

    print(f"\n逐案例诊断：{PREDICTIONS_PATH}")
    print(f"汇总诊断：{SUMMARY_PATH}")


if __name__ == "__main__":
    main()