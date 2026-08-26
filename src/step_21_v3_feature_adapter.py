"""V3：将登记记录与声明字段整理为模型特征，并执行证据门槛检查。"""

from __future__ import annotations

import argparse
import json
from typing import Any

from step_15_registry_lookup import lookup_project


CLAIM_CONTEXTS = [
    "corporate_offset_use",
    "project_status_case",
    "project_total_claim",
]

CLAIM_TONES = [
    "absolute_claim",
    "ambiguous_mixed",
    "honest_specific",
    "neutral_specific",
    "technical_schedule",
    "unsupported_broad",
    "vague_promotional",
]

VERIFIED_AMOUNT_BASES = [
    "retirement_record",
    "issuance_record",
    "registry_line_item",
    "other_traceable",
]

EXPLICIT_RISK_STATUS_WORDS = [
    "cancelled",
    "canceled",
    "terminated",
    "withdrawn",
    "suspended",
    "revoked",
]


def derive_status_risk(registry_status: str | None) -> int | None:
    """仅在状态文本含明确风险词时标记为 1；其他情况不擅自认定为安全。"""
    if not registry_status:
        return None

    normalized_status = registry_status.strip().lower()

    if any(word in normalized_status for word in EXPLICIT_RISK_STATUS_WORDS):
        return 1

    return None


def calculate_discrepancy(
    claimed_amount: float | None,
    verified_amount: float | None,
) -> float | None:
    """只对同一核对口径下的两项数量计算差异比例。"""
    if (
        claimed_amount is None
        or verified_amount is None
        or claimed_amount <= 0
    ):
        return None

    return abs(claimed_amount - verified_amount) / max(abs(claimed_amount), 1.0)


def build_feature_payload(
    project_id: str,
    claimed_amount: float | None,
    claimed_unit: str | None,
    verified_amount: float | None,
    verified_unit: str | None,
    verified_amount_basis: str | None,
    verified_evidence_ref: str | None,
    claim_context: str,
    claim_tone: str,
    status_risk_override: int | None = None,
    status_evidence_ref: str | None = None,
) -> dict[str, Any]:
    """构建模型特征，并明确标记无法安全评分的证据缺口。"""
    project = lookup_project(project_id)
    issues: list[str] = []

    if project is None:
        issues.append("项目 ID 未在本地登记记录快照中精确匹配。")

    if claimed_amount is None or claimed_amount <= 0:
        issues.append("缺少有效的声明数量。")

    if not claimed_unit:
        issues.append("缺少声明数量单位。")

    if verified_amount is None or verified_amount < 0:
        issues.append("缺少与声明对应的已核对数量。")

    if not verified_unit:
        issues.append("缺少已核对数量单位。")

    if claimed_unit and verified_unit and claimed_unit != verified_unit:
        issues.append("声明数量与已核对数量的单位不一致，不能计算差异比例。")

    if not verified_amount_basis:
        issues.append("缺少已核对数量的核对口径。")

    if not verified_evidence_ref:
        issues.append("缺少已核对数量的证据来源说明。")

    registry_status = project["voluntary_status"] if project else None
    derived_status_risk = derive_status_risk(registry_status)

    if status_risk_override is not None:
        status_risk = status_risk_override

        if not status_evidence_ref:
            issues.append("已填写状态风险标记，但缺少状态核验证据来源说明。")
    else:
        status_risk = derived_status_risk

        if status_risk is None:
            issues.append(
                "登记状态未出现明确风险词，且未提供人工核验的状态风险标记。"
            )

    quantities_are_comparable = (
        claimed_amount is not None
        and claimed_amount > 0
        and verified_amount is not None
        and verified_amount >= 0
        and claimed_unit is not None
        and claimed_unit == verified_unit
        and verified_amount_basis is not None
        and verified_evidence_ref is not None
    )

    discrepancy_ratio = (
        calculate_discrepancy(claimed_amount, verified_amount)
        if quantities_are_comparable
        else None
    )

    model_features = {
        "claimed_amount": claimed_amount,
        "registry_amount": verified_amount,
        "issued_credits": (
            project["total_credits_issued"] if project else None
        ),
        "retired_credits": (
            project["total_credits_retired"] if project else None
        ),
        "discrepancy_ratio": discrepancy_ratio,
        "status_risk": status_risk,
        "registry": project["registry"] if project else None,
        "project_type": project["project_type"] if project else None,
        "country": project["country"] if project else None,
        "registry_status": registry_status,
        "claim_context": claim_context,
        "claim_tone": claim_tone,
    }

    source = None
    if project:
        source = {
            "source_workbook": project["source_workbook"],
            "source_sheet": project["source_sheet"],
            "source_excel_row": project["source_excel_row"],
        }

    return {
        "project_id": project_id.strip().upper(),
        "model_features": model_features,
        "quantity_check": {
            "claimed_amount": claimed_amount,
            "claimed_unit": claimed_unit,
            "verified_amount": verified_amount,
            "verified_unit": verified_unit,
            "verified_amount_basis": verified_amount_basis,
            "verified_evidence_ref": verified_evidence_ref,
            "quantities_are_comparable": quantities_are_comparable,
            "discrepancy_ratio": discrepancy_ratio,
        },
        "status_check": {
            "registry_status": registry_status,
            "status_risk": status_risk,
            "status_evidence_ref": status_evidence_ref,
        },
        "registry_aggregate_context": (
            {
                "total_credits_issued": project["total_credits_issued"],
                "total_credits_retired": project["total_credits_retired"],
                "total_credits_remaining": project["total_credits_remaining"],
            }
            if project
            else None
        ),
        "registry_source": source,
        "evidence_gate": {
            "is_ready_for_experimental_score": len(issues) == 0,
            "issues": issues,
            "default_decision": (
                "review_required"
                if issues
                else "experimental_score_allowed"
            ),
        },
    }


def main() -> None:
    """命令行入口：查看特征适配和证据门槛结果。"""
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
    parser.add_argument("--status-risk", type=int, choices=[0, 1])
    parser.add_argument("--status-evidence-ref")
    parser.add_argument(
        "--claim-context",
        required=True,
        choices=CLAIM_CONTEXTS,
    )
    parser.add_argument(
        "--claim-tone",
        required=True,
        choices=CLAIM_TONES,
    )
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
        status_risk_override=args.status_risk,
        status_evidence_ref=args.status_evidence_ref,
    )

    print("=== V3 特征适配与证据门槛 ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()