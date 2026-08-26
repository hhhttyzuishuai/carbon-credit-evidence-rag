"""V3：在证据门槛通过后计算实验性风险分数，但不自动作出企业风险结论。"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from step_18_train_v3_risk_model import MODEL_COLUMNS
from step_21_v3_feature_adapter import (
    CLAIM_CONTEXTS,
    CLAIM_TONES,
    VERIFIED_AMOUNT_BASES,
    build_feature_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "v3_calibrated_structured_audit_xgboost.joblib"
POLICY_PATH = PROJECT_ROOT / "models" / "v3_risk_policy.json"


@lru_cache(maxsize=1)
def load_model():
    """在同一进程中只加载一次当前 V3 模型。"""
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"未找到 V3 模型：{MODEL_PATH}")

    return joblib.load(MODEL_PATH)


@lru_cache(maxsize=1)
def load_policy() -> dict:
    """读取独立校准阶段生成的策略记录，仅用于展示实验背景。"""
    if not POLICY_PATH.is_file():
        raise FileNotFoundError(f"未找到 V3 策略文件：{POLICY_PATH}")

    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def score_payload(payload: dict) -> dict:
    """根据证据门槛决定是否计算实验性模型分数。"""
    evidence_gate = payload["evidence_gate"]

    if not evidence_gate["is_ready_for_experimental_score"]:
        return {
            "decision": "review_required",
            "experimental_high_risk_probability": None,
            "experimental_signal": None,
            "reason": "证据门槛未通过，未调用模型评分。",
            "evidence_issues": evidence_gate["issues"],
            "registry_source": payload["registry_source"],
        }

    model = load_model()
    policy = load_policy()

    feature_frame = pd.DataFrame(
        [
            {
                column: payload["model_features"][column]
                for column in MODEL_COLUMNS
            }
        ]
    )

    probability = float(model.predict_proba(feature_frame)[0, 1])
    high_threshold = policy["policy"]["high_risk_threshold"]
    low_threshold = policy["policy"]["low_risk_threshold"]

    if probability >= high_threshold:
        signal = "above_calibrated_high_risk_threshold"
    elif low_threshold is not None and probability <= low_threshold:
        signal = "below_calibrated_low_risk_threshold"
    else:
        signal = "between_calibrated_thresholds"

    return {
        "decision": "review_required",
        "experimental_high_risk_probability": probability,
        "experimental_signal": signal,
        "reason": (
            "当前模型仅提供实验性风险信号。由于真实验证数据量有限，"
            "系统不依据概率阈值自动输出 low_risk 或 high_risk。"
        ),
        "evidence_issues": [],
        "registry_source": payload["registry_source"],
    }


def main() -> None:
    """命令行入口：特征适配、证据检查与实验性模型评分。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--claimed-amount", type=float)
    parser.add_argument("--claimed-unit")
    parser.add_argument("--verified-amount", type=float)
    parser.add_argument("--verified-unit")
    parser.add_argument(
        "--verified-amount-basis",
        choices=VERIFIED_AMOUNT_BASES,
    )
    parser.add_argument("--verified-evidence-ref")
    parser.add_argument("--claim-context", required=True, choices=CLAIM_CONTEXTS)
    parser.add_argument("--claim-tone", required=True, choices=CLAIM_TONES)
    args = parser.parse_args()

    payload = build_feature_payload(
        project_id=args.project_id,
        claimed_amount=args.claimed_amount,
        claimed_unit=args.claimed_unit,
        verified_amount=args.verified_amount,
        verified_unit=args.verified_unit,
        verified_amount_basis=args.verified_amount_basis,
        verified_evidence_ref=args.verified_evidence_ref,
        claim_context=args.claim_context,
        claim_tone=args.claim_tone,
    )

    result = score_payload(payload)

    print("=== V3 风险审核辅助 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()