"""V3：用独立校准集选择三状态审核策略，并保留最终评估集不参与调参。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from step_18_train_v3_risk_model import (
    MODELS_DIR,
    MODEL_COLUMNS,
    OUTPUTS_DIR,
    build_model,
    file_sha256,
    get_feature_importance,
    load_dataset,
    prepare_features,
)


MODEL_PATH = MODELS_DIR / "v3_calibrated_structured_audit_xgboost.joblib"
POLICY_PATH = MODELS_DIR / "v3_risk_policy.json"
METRICS_PATH = OUTPUTS_DIR / "v3_calibrated_training_metrics.json"
IMPORTANCE_PATH = OUTPUTS_DIR / "v3_calibrated_feature_importance.csv"


def calculate_high_metrics(
    labels: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
) -> dict:
    """把概率大于阈值的样本视为高风险，计算二分类指标。"""
    predictions = (probabilities >= threshold).astype(int)

    return {
        "threshold": float(threshold),
        "predicted_high_risk_count": int(predictions.sum()),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "accuracy": float(accuracy_score(labels, predictions)),
    }


def calculate_low_metrics(
    labels: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
) -> dict:
    """计算被划为低风险的样本中，真实非高风险标签所占比例。"""
    low_mask = probabilities <= threshold
    low_count = int(low_mask.sum())

    if low_count == 0:
        return {
            "threshold": float(threshold),
            "predicted_low_risk_count": 0,
            "negative_predictive_value": None,
        }

    negative_predictive_value = float((labels[low_mask] == 0).mean())

    return {
        "threshold": float(threshold),
        "predicted_low_risk_count": low_count,
        "negative_predictive_value": negative_predictive_value,
    }


def choose_policy(
    labels: pd.Series,
    probabilities: np.ndarray,
    target_precision: float,
    target_negative_predictive_value: float,
) -> dict:
    """仅用校准集选择高风险阈值和低风险阈值。"""
    thresholds = np.linspace(0.01, 0.99, 99)

    high_candidates = [
        calculate_high_metrics(labels, probabilities, threshold)
        for threshold in thresholds
    ]
    high_candidates = [
        result
        for result in high_candidates
        if result["predicted_high_risk_count"] > 0
        and result["precision"] >= target_precision
    ]

    if not high_candidates:
        raise RuntimeError("校准集无法找到满足高风险精确率目标的阈值。")

    # 在满足精确率目标的前提下，选择最低阈值以尽量保留召回率。
    high_policy = min(high_candidates, key=lambda result: result["threshold"])
    high_threshold = high_policy["threshold"]

    low_candidates = [
        calculate_low_metrics(labels, probabilities, threshold)
        for threshold in thresholds
        if threshold < high_threshold
    ]
    low_candidates = [
        result
        for result in low_candidates
        if result["predicted_low_risk_count"] > 0
        and result["negative_predictive_value"]
        >= target_negative_predictive_value
    ]

    # 如果无法安全给出低风险，则保留 None，所有非高风险样本进入人工复核。
    low_policy = (
        max(low_candidates, key=lambda result: result["threshold"])
        if low_candidates
        else None
    )

    return {
        "high_risk_threshold": high_threshold,
        "low_risk_threshold": (
            low_policy["threshold"] if low_policy is not None else None
        ),
        "high_risk_calibration_metrics": high_policy,
        "low_risk_calibration_metrics": low_policy,
    }


def triage_distribution(
    probabilities: np.ndarray,
    low_threshold: float | None,
    high_threshold: float,
) -> dict:
    """将概率映射为 low_risk、review_required、high_risk 三种审核状态。"""
    states = np.full(len(probabilities), "review_required", dtype=object)

    if low_threshold is not None:
        states[probabilities <= low_threshold] = "low_risk"

    states[probabilities >= high_threshold] = "high_risk"

    return {
        state: int((states == state).sum())
        for state in ["low_risk", "review_required", "high_risk"]
    }


def evaluate(
    model,
    frame: pd.DataFrame,
    low_threshold: float | None,
    high_threshold: float,
) -> dict:
    """在未参与阈值选择的数据集上计算指标和三状态分布。"""
    labels = frame["label"].astype(int)
    probabilities = model.predict_proba(prepare_features(frame))[:, 1]

    high_metrics = calculate_high_metrics(
        labels,
        probabilities,
        high_threshold,
    )

    return {
        "cases": int(len(frame)),
        "positive_rate": float(labels.mean()),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "high_risk_binary_metrics": high_metrics,
        "triage_distribution_before_evidence_gate": triage_distribution(
            probabilities,
            low_threshold,
            high_threshold,
        ),
        "missing_claimed_amount_count": int(frame["claimed_amount"].isna().sum()),
    }


def main() -> None:
    """训练、校准并评估 V3 风险审核策略。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-state", type=int, default=72443)
    parser.add_argument("--high-precision-target", type=float, default=0.95)
    parser.add_argument("--low-npv-target", type=float, default=0.95)
    args = parser.parse_args()

    synthetic = load_dataset("synthetic_training")
    stress = load_dataset("generated_stress_test")
    strict = load_dataset("strict_real_validation")

    train_frame, temporary_frame = train_test_split(
        synthetic,
        test_size=0.30,
        stratify=synthetic["label"],
        random_state=args.random_state,
    )

    calibration_frame, holdout_frame = train_test_split(
        temporary_frame,
        test_size=2 / 3,
        stratify=temporary_frame["label"],
        random_state=args.random_state,
    )

    model = build_model(random_state=args.random_state)
    model.fit(
        prepare_features(train_frame),
        train_frame["label"].astype(int),
    )

    calibration_labels = calibration_frame["label"].astype(int)
    calibration_probabilities = model.predict_proba(
        prepare_features(calibration_frame)
    )[:, 1]

    policy = choose_policy(
        labels=calibration_labels,
        probabilities=calibration_probabilities,
        target_precision=args.high_precision_target,
        target_negative_predictive_value=args.low_npv_target,
    )

    evaluations = {
        "synthetic_holdout": evaluate(
            model,
            holdout_frame,
            policy["low_risk_threshold"],
            policy["high_risk_threshold"],
        ),
        "generated_stress_test": evaluate(
            model,
            stress,
            policy["low_risk_threshold"],
            policy["high_risk_threshold"],
        ),
        "strict_real_validation": evaluate(
            model,
            strict,
            policy["low_risk_threshold"],
            policy["high_risk_threshold"],
        ),
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, MODEL_PATH)
    POLICY_PATH.write_text(
        json.dumps(
            {
                "model_type": "structured_audit_xgboost_binary",
                "model_columns": MODEL_COLUMNS,
                "random_state": args.random_state,
                "calibration_cases": int(len(calibration_frame)),
                "policy": policy,
                "evidence_gate": (
                    "项目 ID 未精确核验、关键字段缺失或资料不足时，"
                    "必须覆盖模型输出并返回 review_required。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    get_feature_importance(model).to_csv(IMPORTANCE_PATH, index=False)

    report = {
        "training_cases": int(len(train_frame)),
        "calibration_cases": int(len(calibration_frame)),
        "holdout_cases": int(len(holdout_frame)),
        "data_sha256": {
            name: file_sha256(path)
            for name, path in {
                "synthetic_training": (
                    Path("data/raw/v3_legacy/noisy_synthetic_training_8000.csv")
                ),
                "generated_stress_test": (
                    Path(
                        "data/raw/v3_legacy/"
                        "registry_grounded_generated_line_item_cases_300.csv"
                    )
                ),
                "strict_real_validation": (
                    Path(
                        "data/raw/v3_legacy/"
                        "real_strict_cases_from_previous_project.csv"
                    )
                ),
            }.items()
        },
        "policy": policy,
        "evaluations": evaluations,
        "limitations": [
            "训练数据为合成数据。",
            "压力测试数据为基于登记记录生成的案例。",
            "严格真实验证集仅 16 条。",
            "最终审核结果仍需经过项目 ID 与关键字段证据门槛。",
        ],
    }

    METRICS_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== V3 独立校准训练完成 ===")
    print(f"训练集：{len(train_frame)} 条")
    print(f"校准集：{len(calibration_frame)} 条")
    print(f"留出集：{len(holdout_frame)} 条")
    print(f"低风险阈值：{policy['low_risk_threshold']}")
    print(f"高风险阈值：{policy['high_risk_threshold']}")
    print(f"模型文件：{MODEL_PATH}")
    print(f"策略文件：{POLICY_PATH}")

    for name, result in evaluations.items():
        metrics = result["high_risk_binary_metrics"]
        print(f"\n{name}")
        print(f"  ROC-AUC：{result['roc_auc']:.3f}")
        print(f"  高风险 Precision：{metrics['precision']:.3f}")
        print(f"  高风险 Recall：{metrics['recall']:.3f}")
        print(f"  高风险 F1：{metrics['f1']:.3f}")
        print(
            "  三状态分布："
            f"{result['triage_distribution_before_evidence_gate']}"
        )


if __name__ == "__main__":
    main()