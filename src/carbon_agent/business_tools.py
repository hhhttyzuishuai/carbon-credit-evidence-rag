"""Typed adapters around the existing registry and risk-review business tools."""

from __future__ import annotations

from typing import Any, Protocol


class RegistryLookup(Protocol):
    def lookup(self, project_id: str) -> dict[str, Any] | None:
        """Return one exact project record from the local snapshot."""


class RiskReviewer(Protocol):
    def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run evidence gating and, only when allowed, experimental scoring."""


class LocalRegistryTool:
    def lookup(self, project_id: str) -> dict[str, Any] | None:
        from step_15_registry_lookup import lookup_project

        return lookup_project(project_id)


class ExperimentalRiskTool:
    def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        from step_21_v3_feature_adapter import build_feature_payload
        from step_23_v3_risk_scorer import score_payload

        feature_payload = build_feature_payload(
            project_id=str(payload.get("project_id", "")),
            claimed_amount=payload.get("claimed_amount"),
            claimed_unit=payload.get("claimed_unit"),
            verified_amount=payload.get("verified_amount"),
            verified_unit=payload.get("verified_unit"),
            verified_amount_basis=payload.get("verified_amount_basis"),
            verified_evidence_ref=payload.get("verified_evidence_ref"),
            claim_context=str(payload.get("claim_context", "")),
            claim_tone=str(payload.get("claim_tone", "")),
            status_risk_override=payload.get("status_risk_override"),
            status_evidence_ref=payload.get("status_evidence_ref"),
        )
        return {
            "feature_payload": feature_payload,
            "review_result": score_payload(feature_payload),
        }

