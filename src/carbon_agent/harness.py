"""V5 production-like agent harness with a bounded observe/act loop."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any

from .audit import JsonlAuditLog
from .context import ArtifactStore, ContextWindowManager
from .contracts import AgentRequest, AgentResponse, Message, Source
from .execution_store import SQLiteExecutionStore
from .memory import SQLiteConversationStore
from .planner import ToolPlanner
from .tooling import (
    ToolApprovalRequired,
    ToolContext,
    ToolRegistry,
    ToolValidationError,
)


SYSTEM_PROMPT = """你是碳信用证据核查 Agent。你可以自主选择已注册工具，但必须遵守：
1. 需要本地文档或登记信息支撑的事实，先调用工具，再使用工具给出的 [S编号] 或 [T编号] 引用。
2. 对话历史只帮助理解意图，不是事实证据。
3. 不得把实验性风险信号表述为绿洗、违法或合规结论。
4. 工具失败或参数错误时，可以修正参数或换一种路径；信息不足时明确说明。
5. 已经足够回答时直接结束，不得为了展示能力而无意义调用工具。
不要输出隐藏推理过程，只输出工具调用或给用户的最终回答。"""


class AgentHarness:
    """Coordinate planning, tools, durable state, policy checks, and replay."""

    def __init__(
        self,
        planner: ToolPlanner,
        tools: ToolRegistry,
        execution_store: SQLiteExecutionStore,
        conversation_store: SQLiteConversationStore,
        context_manager: ContextWindowManager,
        artifact_store: ArtifactStore,
        audit_log: JsonlAuditLog | None = None,
        max_steps: int = 6,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps 至少为 1。")
        self.planner = planner
        self.tools = tools
        self.execution_store = execution_store
        self.conversation_store = conversation_store
        self.context_manager = context_manager
        self.artifact_store = artifact_store
        self.audit_log = audit_log
        self.max_steps = max_steps

    def handle(self, request: AgentRequest) -> AgentResponse:
        fingerprint = self._fingerprint(request)
        record = self.execution_store.begin(request.request_id, fingerprint)
        if record.status == "completed" and record.response:
            response = self._response_from_dict(record.response)
            response.metadata = {**response.metadata, "idempotent_replay": True}
            return response

        recovered = not record.is_new and bool(record.checkpoint)
        if recovered:
            state = self._restore_state(record.checkpoint)
        else:
            session_id = self.conversation_store.create_session(request.session_id)
            messages = [
                Message(role="system", content=SYSTEM_PROMPT),
                *self.conversation_store.get_history(session_id),
                Message(role="user", content=self._user_prompt(request)),
            ]
            state = {
                "session_id": session_id,
                "messages": messages,
                "sources": [],
                "tool_calls": [],
                "artifacts": [],
                "compacted_messages": 0,
            }
            self._save_checkpoint(request.request_id, 0, state)

        try:
            start_step = record.step + 1 if recovered else 1
            for step in range(start_step, self.max_steps + 1):
                compacted = self.context_manager.compact(state["messages"])
                state["compacted_messages"] += compacted.compacted_messages
                decision = self.planner.decide(
                    compacted.messages, self.tools.list_specs()
                )
                self.execution_store.append_event(
                    request.request_id,
                    "planner_decision",
                    {"step": step, "action": decision.action, "tool": decision.tool_name},
                )

                if decision.action == "final":
                    return self._complete(
                        request,
                        state,
                        decision.answer or "当前无法形成可靠回答。",
                        step,
                        recovered,
                    )

                if decision.action != "tool" or not decision.tool_name:
                    raise RuntimeError("规划器返回了不支持的动作。")

                try:
                    spec = self.tools.get(decision.tool_name)
                except ToolValidationError as error:
                    self._append_tool_error(state, decision.tool_name, str(error))
                    self._save_checkpoint(request.request_id, step, state)
                    continue

                context = ToolContext(
                    actor_id=request.actor_id,
                    request_id=request.request_id,
                    approval_granted=request.approval_granted,
                )
                result = None
                last_error: Exception | None = None
                for attempt in range(spec.max_retries + 1):
                    try:
                        result = self.tools.execute(
                            decision.tool_name, decision.arguments, context
                        )
                        break
                    except ToolApprovalRequired as error:
                        self.execution_store.append_event(
                            request.request_id,
                            "approval_required",
                            {"step": step, "tool": decision.tool_name},
                        )
                        return self._complete(
                            request,
                            state,
                            f"该操作需要显式人工授权后才能执行：{error}",
                            step,
                            recovered,
                            extra_metadata={"approval_required": True},
                        )
                    except Exception as error:
                        last_error = error
                        if attempt < spec.max_retries:
                            self.execution_store.append_event(
                                request.request_id,
                                "tool_retry",
                                {
                                    "step": step,
                                    "tool": decision.tool_name,
                                    "attempt": attempt + 1,
                                    "error_type": type(error).__name__,
                                },
                            )

                if result is None:
                    self._append_tool_error(
                        state,
                        decision.tool_name,
                        f"{type(last_error).__name__}: {last_error}",
                    )
                    self._record_tool_call(
                        state,
                        decision.tool_name,
                        decision.arguments,
                        "error",
                        step,
                    )
                    self._save_checkpoint(request.request_id, step, state)
                    continue

                observation = self.artifact_store.externalize(
                    request.request_id,
                    step,
                    {
                        "tool": decision.tool_name,
                        "content": result.content,
                        "metadata": result.metadata,
                    },
                )
                state["messages"].append(
                    Message(
                        role="system",
                        name="tool_observation",
                        content=(
                            f"工具 {decision.tool_name} 的执行结果："
                            f"{observation.model_text}"
                        ),
                    )
                )
                self._merge_sources(state["sources"], result.sources)
                if observation.artifact:
                    state["artifacts"].append(observation.artifact)
                self._record_tool_call(
                    state,
                    decision.tool_name,
                    decision.arguments,
                    "success",
                    step,
                )
                self.execution_store.append_event(
                    request.request_id,
                    "tool_completed",
                    {
                        "step": step,
                        "tool": decision.tool_name,
                        "source_count": len(result.sources),
                        "externalized": observation.artifact is not None,
                    },
                )
                self._save_checkpoint(request.request_id, step, state)

            return self._complete(
                request,
                state,
                "已达到最大执行步数，系统已停止继续调用工具，请人工复核或缩小问题范围。",
                self.max_steps,
                recovered,
                extra_metadata={"max_steps_reached": True},
            )
        except Exception as error:
            self.execution_store.fail(request.request_id, type(error).__name__)
            self._audit(
                {
                    "event": "execution_failed",
                    "request_id": request.request_id,
                    "error_type": type(error).__name__,
                }
            )
            return AgentResponse(
                answer=(
                    "本次执行在完成前中断，已保存最近检查点。使用相同 request_id "
                    "重试时会从检查点恢复。"
                ),
                agent="v5_harness_agent",
                session_id=state.get("session_id"),
                sources=state.get("sources", []),
                tool_calls=state.get("tool_calls", []),
                metadata={
                    "version": "v5",
                    "status": "failed",
                    "recoverable": True,
                    "error_type": type(error).__name__,
                },
            )

    def get_events(self, request_id: str) -> list[dict[str, Any]]:
        return self.execution_store.get_events(request_id)

    def _complete(
        self,
        request: AgentRequest,
        state: dict[str, Any],
        answer: str,
        step: int,
        recovered: bool,
        extra_metadata: dict[str, Any] | None = None,
    ) -> AgentResponse:
        answer, verification = self._verify_answer(answer, state)
        response = AgentResponse(
            answer=answer,
            agent="v5_harness_agent",
            session_id=state["session_id"],
            sources=state["sources"],
            tool_calls=state["tool_calls"],
            metadata={
                "version": "v5",
                "status": "completed",
                "steps": step,
                "recovered_from_checkpoint": recovered,
                "idempotent_replay": False,
                "compacted_messages": state["compacted_messages"],
                "artifacts": state["artifacts"],
                "citation_verification": verification,
                **(extra_metadata or {}),
            },
        )
        self.conversation_store.record_turn(
            state["session_id"], request.text, response.answer
        )
        self.execution_store.complete(request.request_id, response.to_dict())
        self._audit(
            {
                "event": "execution_completed",
                "request_id": request.request_id,
                "session_id": state["session_id"],
                "steps": step,
                "tools": [call["name"] for call in state["tool_calls"]],
            }
        )
        return response

    @staticmethod
    def _verify_answer(answer: str, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        evidence_tools = {
            call["name"]
            for call in state["tool_calls"]
            if call["status"] == "success"
            and call["name"] in {"knowledge_search", "registry_lookup"}
        }
        valid_ids = {source.source_id for source in state["sources"]}
        cited_ids = set(re.findall(r"\[([ST]\d+)\]", answer))
        invalid = sorted(cited_ids - valid_ids)
        missing = bool(evidence_tools and valid_ids and not (cited_ids & valid_ids))
        passed = not invalid and not missing
        if not passed:
            answer = (
                "输出引用校验未通过，系统没有把该回答作为可靠结论返回。"
                f"可用证据编号：{', '.join(sorted(valid_ids)) or '无'}。"
            )
        return answer, {
            "passed": passed,
            "valid_source_ids": sorted(valid_ids),
            "cited_source_ids": sorted(cited_ids),
            "invalid_source_ids": invalid,
            "missing_required_citation": missing,
        }

    @staticmethod
    def _fingerprint(request: AgentRequest) -> str:
        payload = {
            "text": request.text,
            "session_id": request.session_id,
            "actor_id": request.actor_id,
            "intent": request.intent,
            "payload": request.payload,
            "approval_granted": request.approval_granted,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _user_prompt(request: AgentRequest) -> str:
        payload = json.dumps(request.payload, ensure_ascii=False, sort_keys=True)
        return (
            f"用户问题：{request.text}\n"
            f"期望意图：{request.intent}\n"
            f"结构化参数：{payload}\n"
            f"高风险工具授权：{request.approval_granted}"
        )

    @staticmethod
    def _record_tool_call(
        state: dict[str, Any],
        name: str,
        arguments: dict[str, Any],
        status: str,
        step: int,
    ) -> None:
        state["tool_calls"].append(
            {"name": name, "arguments": arguments, "status": status, "step": step}
        )

    @staticmethod
    def _append_tool_error(state: dict[str, Any], name: str, error: str) -> None:
        state["messages"].append(
            Message(
                role="system",
                name="tool_observation",
                content=f"工具 {name} 执行失败：{error}。请修正参数或换一种路径。",
            )
        )

    @staticmethod
    def _merge_sources(existing: list[Source], incoming: list[Source]) -> None:
        known = {source.source_id for source in existing}
        for source in incoming:
            if source.source_id not in known:
                existing.append(source)
                known.add(source.source_id)

    def _save_checkpoint(
        self, request_id: str, step: int, state: dict[str, Any]
    ) -> None:
        payload = {
            "session_id": state["session_id"],
            "messages": [asdict(message) for message in state["messages"]],
            "sources": [asdict(source) for source in state["sources"]],
            "tool_calls": state["tool_calls"],
            "artifacts": state["artifacts"],
            "compacted_messages": state["compacted_messages"],
        }
        self.execution_store.save_checkpoint(request_id, step, payload)

    @staticmethod
    def _restore_state(checkpoint: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": checkpoint["session_id"],
            "messages": [Message(**item) for item in checkpoint.get("messages", [])],
            "sources": [Source(**item) for item in checkpoint.get("sources", [])],
            "tool_calls": checkpoint.get("tool_calls", []),
            "artifacts": checkpoint.get("artifacts", []),
            "compacted_messages": checkpoint.get("compacted_messages", 0),
        }

    @staticmethod
    def _response_from_dict(payload: dict[str, Any]) -> AgentResponse:
        return AgentResponse(
            answer=payload["answer"],
            agent=payload["agent"],
            trace_id=payload["trace_id"],
            session_id=payload.get("session_id"),
            sources=[Source(**item) for item in payload.get("sources", [])],
            tool_calls=payload.get("tool_calls", []),
            metadata=payload.get("metadata", {}),
            created_at=payload["created_at"],
        )

    def _audit(self, event: dict[str, Any]) -> None:
        if self.audit_log:
            self.audit_log.write(event)
