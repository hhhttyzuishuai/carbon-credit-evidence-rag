"""V3：使用论文结构化审核特征，在当前环境重新训练 XGBoost 风险模型。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "v3_legacy"
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

NUMERIC_COLUMNS = [
    "claimed_amount",
    "registry_amount",
    "issued_credits",
    "retired_credits",
    "discrepancy_ratio",
    "status_risk",
]

CATEGORICAL_COLUMNS = [
    "registry",
    "project_type",
    "country",
    "registry_status",
    "claim_context",
    "claim_tone",
]

MODEL_COLUMNS = NUMERIC_COLUMNS + CATEGORICAL_COLUMNS

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
    """计算输入数据哈希，保证训练结果可追溯。"""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def load_dataset(name: str) -> pd.DataFrame:
    """读取并检查一个 V3 数据集。"""
    file_path = DATASETS[name]
    frame = pd.read_csv(file_path)

    missing_columns = [
        column
        for column in MODEL_COLUMNS + ["label"]
        if column not in frame.columns
    ]
    if missing_columns:
        raise ValueError(f"{name} 缺少字段：{missing_columns}")

    return frame


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    """统一数值与类别字段格式，缺失值由后续 Pipeline 按训练集策略处理。"""
    features = frame[MODEL_COLUMNS].copy()

    for column in NUMERIC_COLUMNS:
        features[column] = pd.to_numeric(features[column], errors="coerce")

    for column in CATEGORICAL_COLUMNS:
        features[column] = features[column].astype("object")

    return features


def build_model(random_state: int) -> Pipeline:
    """构建仅使用结构化审核特征的 XGBoost Pipeline。"""
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", max_categories=40)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_COLUMNS),
            ("categorical", categorical_pipeline, CATEGORICAL_COLUMNS),
        ],
        remainder="drop",
        sparse_threshold=0.3,
    )

    classifier = XGBClassifier(
        n_estimators=160,
        max_depth=3,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.5,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=random_state,
        n_jobs=4,
    )

    return Pipeline(
        steps=[
            ("features", preprocessor),
            ("classifier", classifier),
        ]
    )


def evaluate(model: Pipeline, frame: pd.DataFrame) -> dict:
    """计算二分类模型在一个数据集上的指标。"""
    features = prepare_features(frame)
    labels = frame["label"].astype(int)

    predictions = model.predict(features)
    probabilities = model.predict_proba(features)[:, 1]

    try:
        roc_auc = float(roc_auc_score(labels, probabilities))
    except ValueError:
        roc_auc = None

    return {
        "cases": int(len(frame)),
        "positive_rate": float(labels.mean()),
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "roc_auc": roc_auc,
        "confusion_matrix": confusion_matrix(labels, predictions).tolist(),
    }


def get_feature_importance(model: Pipeline) -> pd.DataFrame:
    """导出训练完成后的结构化特征重要性。"""
    preprocessor = model.named_steps["features"]
    classifier = model.named_steps["classifier"]

    numeric_names = [f"numeric__{column}" for column in NUMERIC_COLUMNS]

    onehot = preprocessor.named_transformers_["categorical"].named_steps["onehot"]
    categorical_names = [
        f"categorical__{name}"
        for name in onehot.get_feature_names_out(CATEGORICAL_COLUMNS)
    ]

    names = numeric_names + categorical_names
    importances = classifier.feature_importances_
    size = min(len(names), len(importances))

    return (
        pd.DataFrame(
            {
                "feature": names[:size],
                "importance": importances[:size],
            }
        )
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def main() -> None:
    """训练模型，并输出三类评估集上的结果。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-state", type=int, default=72443)
    parser.add_argument("--test-size", type=float, default=0.22)
    args = parser.parse_args()

    training_frame = load_dataset("synthetic_training")
    stress_frame = load_dataset("generated_stress_test")
    strict_frame = load_dataset("strict_real_validation")

    train_frame, holdout_frame = train_test_split(
        training_frame,
        test_size=args.test_size,
        stratify=training_frame["label"],
        random_state=args.random_state,
    )

    model = build_model(random_state=args.random_state)
    model.fit(
        prepare_features(train_frame),
        train_frame["label"].astype(int),
    )

    evaluations = {
        "synthetic_holdout": evaluate(model, holdout_frame),
        "generated_stress_test": evaluate(model, stress_frame),
        "strict_real_validation": evaluate(model, strict_frame),
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODELS_DIR / "v3_structured_audit_xgboost.joblib"
    metrics_path = OUTPUTS_DIR / "v3_training_metrics.json"
    importance_path = OUTPUTS_DIR / "v3_feature_importance.csv"

    joblib.dump(model, model_path)
    get_feature_importance(model).to_csv(importance_path, index=False)

    report = {
        "model_type": "structured_audit_xgboost_binary",
        "xgboost_version": xgboost.__version__,
        "random_state": args.random_state,
        "test_size": args.test_size,
        "model_columns": MODEL_COLUMNS,
        "class_meaning": {
            "0": "non_high_risk_signal",
            "1": "high_risk_signal",
        },
        "data_sha256": {
            name: file_sha256(path)
            for name, path in DATASETS.items()
        },
        "evaluations": evaluations,
        "important_limitations": [
            "训练集为合成数据。",
            "压力测试集为基于登记记录生成的案例。",
            "严格真实验证集只有 16 条，不足以证明通用泛化能力。",
            "review_required 是后续证据门槛和概率区间产生的审核状态，不是模型原生类别。",
        ],
    }

    metrics_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== V3 结构化风险模型训练完成 ===")
    print(f"XGBoost 版本：{xgboost.__version__}")
    print(f"模型文件：{model_path}")
    print(f"指标文件：{metrics_path}")
    print(f"特征重要性：{importance_path}")

    for name, result in evaluations.items():
        print(f"\n{name}")
        print(f"  cases: {result['cases']}")
        print(f"  accuracy: {result['accuracy']:.3f}")
        print(f"  precision: {result['precision']:.3f}")
        print(f"  recall: {result['recall']:.3f}")
        print(f"  f1: {result['f1']:.3f}")
        print(f"  roc_auc: {result['roc_auc']}")


if __name__ == "__main__":
    main()