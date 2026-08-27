"""V5 typed tool registry and adapters for all business capabilities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .business_tools import ExperimentalRiskTool, LocalRegistryTool
from .contracts import Source
from .knowledge import KnowledgeRetriever


JSONSchema = dict[str, Any]


@dataclass(frozen=True)
class ToolContext:
    actor_id: str
    request_id: str
    approval_granted: bool = False


@dataclass
class ToolResult:
    content: dict[str, Any]
    sources: list[Source] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def observation_text(self) -> str:
        return json.dumps(self.content, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: JSONSchema
    handler: Callable[[dict[str, Any], ToolContext], ToolResult]
    requires_approval: bool = False
    max_retries: int = 1

    def as_model_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolValidationError(ValueError):
    pass


class ToolApprovalRequired(PermissionError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具已注册：{spec.name}")
        self._tools[spec.name] = spec

    def list_specs(self) -> list[ToolSpec]:
        return [self._tools[name] for name in sorted(self._tools)]

    def model_tools(self) -> list[dict[str, Any]]:
        return [spec.as_model_tool() for spec in self.list_specs()]

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ToolValidationError(f"未知工具：{name}") from error

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        spec = self.get(name)
        self._validate_arguments(spec, arguments)
        if spec.requires_approval and not context.approval_granted:
            raise ToolApprovalRequired(f"工具 {name} 需要显式人工授权。")
        return spec.handler(arguments, context)

    @staticmethod
    def _validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ToolValidationError("工具参数必须是 JSON 对象。")
        schema = spec.parameters
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            raise ToolValidationError(
                f"工具 {spec.name} 缺少必填参数：{', '.join(missing)}"
            )
        unexpected = sorted(set(arguments) - set(properties))
        if unexpected:
            raise ToolValidationError(
                f"工具 {spec.name} 包含未知参数：{', '.join(unexpected)}"
            )
        for name, value in arguments.items():
            expected = properties.get(name, {}).get("type")
            valid = {
                "string": isinstance(value, str),
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                "boolean": isinstance(value, bool),
                "object": isinstance(value, dict),
            }.get(expected, True)
            if not valid:
                raise ToolValidationError(
                    f"工具 {spec.name} 参数 {name} 类型应为 {expected}。"
                )


def build_default_tool_registry(
    retriever: KnowledgeRetriever,
    registry_tool: LocalRegistryTool | None = None,
    risk_tool: ExperimentalRiskTool | None = None,
) -> ToolRegistry:
    registry_backend = registry_tool or LocalRegistryTool()
    risk_backend = risk_tool or ExperimentalRiskTool()
    registry = ToolRegistry()

    def knowledge_search(args: dict[str, Any], _: ToolContext) -> ToolResult:
        evidence = retriever.retrieve(args["query"], top_k=args.get("top_k", 5))
        items = [
            {
                "citation": item.citation,
                "text": item.text,
                "source_file": item.source_file,
                "physical_page": item.page_number,
                "document_type": item.document_type,
                "language": item.language,
                "score": item.score,
            }
            for item in evidence
        ]
        sources = [
            Source(
                source_id=item.evidence_id,
                label=item.source_file,
                locator=f"physical_page:{item.page_number}",
                preview=item.text[:500],
            )
            for item in evidence
        ]
        return ToolResult(
            content={
                "evidence": items,
                "instruction": "回答事实时必须引用对应的 [S编号]。",
            },
            sources=sources,
            metadata={"evidence_count": len(items)},
        )

    def registry_lookup(args: dict[str, Any], _: ToolContext) -> ToolResult:
        project_id = args["project_id"].strip().upper().replace("-", "")
        project = registry_backend.lookup(project_id)
        if project is None:
            return ToolResult(
                content={
                    "project_id": project_id,
                    "found": False,
                    "message": "本地静态快照未精确匹配，需要人工复核。",
                },
                metadata={"snapshot_is_realtime": False},
            )
        source = Source(
            source_id="T1",
            label=str(project.get("source_workbook", "registry snapshot")),
            locator=(
                f"sheet:{project.get('source_sheet')};"
                f"excel_row:{project.get('source_excel_row')}"
            ),
            preview=json.dumps(project, ensure_ascii=False)[:500],
        )
        return ToolResult(
            content={
                "found": True,
                "project": project,
                "warning": "这是本地静态快照，不代表登记机构实时状态。",
                "citation": "[T1]",
            },
            sources=[source],
            metadata={"snapshot_is_realtime": False},
        )

    def risk_review(args: dict[str, Any], _: ToolContext) -> ToolResult:
        result = risk_backend.review(args)
        review = result["review_result"]
        source_payload = review.get("registry_source")
        sources = []
        if source_payload:
            sources.append(
                Source(
                    source_id="T1",
                    label=str(source_payload.get("source_workbook")),
                    locator=(
                        f"sheet:{source_payload.get('source_sheet')};"
                        f"excel_row:{source_payload.get('source_excel_row')}"
                    ),
                )
            )
        return ToolResult(
            content={
                **result,
                "mandatory_notice": (
                    "仅提供实验性审核信号，不构成绿洗、违法或合规结论。"
                ),
            },
            sources=sources,
        )

    registry.register(
        ToolSpec(
            name="knowledge_search",
            description=(
                "检索本地碳信用 PDF 知识库，返回带文件名和物理页码的证据。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题"},
                    "top_k": {"type": "integer", "description": "返回证据数量"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=knowledge_search,
        )
    )
    registry.register(
        ToolSpec(
            name="registry_lookup",
            description="按 Project ID 精确查询本地碳信用登记记录静态快照。",
            parameters={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "项目编号"}
                },
                "required": ["project_id"],
                "additionalProperties": False,
            },
            handler=registry_lookup,
        )
    )
    registry.register(
        ToolSpec(
            name="experimental_risk_review",
            description=(
                "对证据完整的碳信用声明生成实验性审核信号。必须经过人工授权，"
                "且永远不能输出绿洗、违法或合规结论。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "claimed_amount": {"type": "number"},
                    "claimed_unit": {"type": "string"},
                    "verified_amount": {"type": "number"},
                    "verified_unit": {"type": "string"},
                    "verified_amount_basis": {"type": "string"},
                    "verified_evidence_ref": {"type": "string"},
                    "claim_context": {"type": "string"},
                    "claim_tone": {"type": "string"},
                    "status_risk_override": {"type": "integer"},
                    "status_evidence_ref": {"type": "string"},
                },
                "required": ["project_id", "claim_context", "claim_tone"],
                "additionalProperties": False,
            },
            handler=risk_review,
            requires_approval=True,
            max_retries=0,
        )
    )
    return registry
