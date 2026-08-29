"""V6 LangGraph runtime reusing the project's evidence and policy contracts."""

from __future__ import annotations

import importlib.metadata
from dataclasses import asdict
from typing import Any, TypedDict

from .audit import JsonlAuditLog
from .context import ArtifactStore, ContextWindowManager
from .contracts import AgentRequest, AgentResponse, Message, Source
from .execution_store import SQLiteExecutionStore
from .harness import AgentHarness, SYSTEM_PROMPT
from .langchain_adapter import langchain_tool_from_spec
from .memory import SQLiteConversationStore
from .planner import ToolPlanner
from .tooling import (
    ToolApprovalRequired,
    ToolContext,
    ToolRegistry,
    ToolValidationError,
)
from .verification import verify_grounded_answer


class GraphState(TypedDict, total=False):
    request: dict[str, Any]
    session_id: str
    messages: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    compacted_messages: int
    step: int
    decision: dict[str, Any]
    answer: str
    status: str
    citation_verification: dict[str, Any]


class LangGraphAgentRuntime:
    """StateGraph orchestration with standard checkpointing and conditional edges."""

    GRAPH_NODES = ["planner", "tool_executor", "output_verifier"]
    GRAPH_EDGES = [
        ("START", "planner"),
        ("planner", "tool_executor", "tool"),
        ("planner", "output_verifier", "final"),
        ("tool_executor", "planner", "continue"),
        ("tool_executor", "output_verifier", "stop"),
        ("output_verifier", "END"),
    ]

    def __init__(
        self,
        planner: ToolPlanner,
        tools: ToolRegistry,
        execution_store: SQLiteExecutionStore,
        conversation_store: SQLiteConversationStore,
        context_manager: ContextWindowManager,
        artifact_store: ArtifactStore,
        checkpointer: Any,
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
        self.checkpointer = checkpointer
        self.audit_log = audit_log
        self.max_steps = max_steps
        self.graph = self._build_graph()

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as error:
            raise RuntimeError("V6 需要安装 langgraph。") from error

        builder = StateGraph(GraphState)
        builder.add_node("planner", self._planner_node)
        builder.add_node("tool_executor", self._tool_node)
        builder.add_node("output_verifier", self._verifier_node)
        builder.add_edge(START, "planner")
        builder.add_conditional_edges(
            "planner",
            self._route_after_planner,
            {"tool": "tool_executor", "final": "output_verifier"},
        )
        builder.add_conditional_edges(
            "tool_executor",
            self._route_after_tool,
            {"continue": "planner", "stop": "output_verifier"},
        )
        builder.add_edge("output_verifier", END)
        return builder.compile(checkpointer=self.checkpointer)

    def handle(self, request: AgentRequest) -> AgentResponse:
        fingerprint = AgentHarness._fingerprint(request)
        record = self.execution_store.begin(request.request_id, fingerprint)
        if record.status == "completed" and record.response:
            response = AgentHarness._response_from_dict(record.response)
            response.metadata = {**response.metadata, "idempotent_replay": True}
            return response

        recovered = not record.is_new
        config = {
            "configurable": {"thread_id": request.request_id},
            "recursion_limit": self.max_steps * 3 + 6,
        }
        try:
            if recovered:
                state = self.graph.invoke(None, config=config)
            else:
                session_id = self.conversation_store.create_session(
                    request.session_id
                )
                initial_state: GraphState = {
                    "request": asdict(request),
                    "session_id": session_id,
                    "messages": [
                        asdict(Message(role="system", content=SYSTEM_PROMPT)),
                        *[
                            asdict(message)
                            for message in self.conversation_store.get_history(
                                session_id
                            )
                        ],
                        asdict(
                            Message(
                                role="user",
                                content=AgentHarness._user_prompt(request),
                            )
                        ),
                    ],
                    "sources": [],
                    "tool_calls": [],
                    "artifacts": [],
                    "compacted_messages": 0,
                    "step": 0,
                    "status": "running",
                }
                self.execution_store.save_checkpoint(
                    request.request_id,
                    0,
                    {"graph_thread_id": request.request_id, "runtime": "langgraph"},
                )
                state = self.graph.invoke(initial_state, config=config)

            return self._complete(request, state, recovered)
        except Exception as error:
            self.execution_store.fail(request.request_id, type(error).__name__)
            self._audit(
                {
                    "event": "langgraph_execution_failed",
                    "request_id": request.request_id,
                    "error_type": type(error).__name__,
                }
            )
            return AgentResponse(
                answer=(
                    "V6 工作流在完成前中断，LangGraph 已保存节点状态。使用相同 "
                    "request_id 重试时会从失败节点恢复。"
                ),
                agent="v6_langgraph_agent",
                session_id=request.session_id,
                metadata={
                    "version": "v6",
                    "runtime": "langgraph",
                    "status": "failed",
                    "recoverable": True,
                    "error_type": type(error).__name__,
                },
            )

    def _planner_node(self, state: GraphState) -> GraphState:
        step = int(state.get("step", 0))
        if step >= self.max_steps:
            return {
                "decision": {"action": "final"},
                "answer": (
                    "已达到最大执行步数，工作流已停止，请人工复核或缩小问题范围。"
                ),
                "status": "max_steps_reached",
            }

        messages = [Message(**item) for item in state.get("messages", [])]
        compacted = self.context_manager.compact(messages)
        decision = self.planner.decide(
            compacted.messages, self.tools.list_specs()
        )
        next_step = step + 1
        request_id = state["request"]["request_id"]
        self.execution_store.append_event(
            request_id,
            "langgraph_node_completed",
            {
                "node": "planner",
                "step": next_step,
                "action": decision.action,
                "tool": decision.tool_name,
            },
        )
        self.execution_store.save_checkpoint(
            request_id,
            next_step,
            {"graph_thread_id": request_id, "node": "planner"},
        )
        return {
            "decision": {
                "action": decision.action,
                "tool_name": decision.tool_name,
                "arguments": decision.arguments,
            },
            "answer": decision.answer or "",
            "step": next_step,
            "compacted_messages": int(state.get("compacted_messages", 0))
            + compacted.compacted_messages,
        }

    @staticmethod
    def _route_after_planner(state: GraphState) -> str:
        return "tool" if state.get("decision", {}).get("action") == "tool" else "final"

    def _tool_node(self, state: GraphState) -> GraphState:
        decision = state.get("decision", {})
        tool_name = str(decision.get("tool_name") or "")
        arguments = dict(decision.get("arguments") or {})
        request_payload = state["request"]
        request_id = request_payload["request_id"]
        step = int(state.get("step", 0))
        tool_calls = list(state.get("tool_calls", []))

        try:
            spec = self.tools.get(tool_name)
        except ToolValidationError as error:
            return self._tool_error_update(
                state, tool_name, arguments, step, str(error)
            )

        context = ToolContext(
            actor_id=request_payload.get("actor_id", "local-user"),
            request_id=request_id,
            approval_granted=bool(request_payload.get("approval_granted", False)),
        )

        def execute(args: dict[str, Any]) -> dict[str, Any]:
            result = self.tools.execute(tool_name, args, context)
            return {
                "content": result.content,
                "sources": [asdict(source) for source in result.sources],
                "metadata": result.metadata,
            }

        langchain_tool = langchain_tool_from_spec(spec, execute)
        result_payload = None
        last_error: Exception | None = None
        for attempt in range(spec.max_retries + 1):
            try:
                result_payload = langchain_tool.invoke(arguments)
                break
            except ToolApprovalRequired as error:
                self.execution_store.append_event(
                    request_id,
                    "langgraph_approval_required",
                    {"node": "tool_executor", "step": step, "tool": tool_name},
                )
                return {
                    "answer": f"该工具需要显式人工授权后才能执行：{error}",
                    "status": "approval_required",
                }
            except Exception as error:
                last_error = error
                if attempt < spec.max_retries:
                    self.execution_store.append_event(
                        request_id,
                        "langgraph_tool_retry",
                        {
                            "node": "tool_executor",
                            "step": step,
                            "tool": tool_name,
                            "attempt": attempt + 1,
                            "error_type": type(error).__name__,
                        },
                    )

        if result_payload is None:
            return self._tool_error_update(
                state,
                tool_name,
                arguments,
                step,
                f"{type(last_error).__name__}: {last_error}",
            )

        observation = self.artifact_store.externalize(
            request_id,
            step,
            {
                "tool": tool_name,
                "content": result_payload["content"],
                "metadata": result_payload["metadata"],
            },
        )
        messages = list(state.get("messages", []))
        messages.append(
            asdict(
                Message(
                    role="system",
                    name="tool_observation",
                    content=f"工具 {tool_name} 的执行结果：{observation.model_text}",
                )
            )
        )
        sources = self._merge_source_dicts(
            state.get("sources", []), result_payload["sources"]
        )
        tool_calls.append(
            {
                "name": tool_name,
                "arguments": arguments,
                "status": "success",
                "step": step,
                "executor": "langchain_structured_tool",
            }
        )
        artifacts = list(state.get("artifacts", []))
        if observation.artifact:
            artifacts.append(observation.artifact)
        self.execution_store.append_event(
            request_id,
            "langgraph_node_completed",
            {
                "node": "tool_executor",
                "step": step,
                "tool": tool_name,
                "source_count": len(result_payload["sources"]),
            },
        )
        self.execution_store.save_checkpoint(
            request_id,
            step,
            {"graph_thread_id": request_id, "node": "tool_executor"},
        )
        update: GraphState = {
            "messages": messages,
            "sources": sources,
            "tool_calls": tool_calls,
            "artifacts": artifacts,
            "status": "running",
        }
        if step >= self.max_steps:
            update["answer"] = (
                "已达到最大执行步数，工作流已停止，请人工复核或缩小问题范围。"
            )
            update["status"] = "max_steps_reached"
        return update

    def _tool_error_update(
        self,
        state: GraphState,
        tool_name: str,
        arguments: dict[str, Any],
        step: int,
        error: str,
    ) -> GraphState:
        messages = list(state.get("messages", []))
        messages.append(
            asdict(
                Message(
                    role="system",
                    name="tool_observation",
                    content=(
                        f"工具 {tool_name} 执行失败：{error}。"
                        "请修正参数或选择其他路径。"
                    ),
                )
            )
        )
        tool_calls = list(state.get("tool_calls", []))
        tool_calls.append(
            {
                "name": tool_name,
                "arguments": arguments,
                "status": "error",
                "step": step,
                "executor": "langchain_structured_tool",
            }
        )
        request_id = state["request"]["request_id"]
        self.execution_store.append_event(
            request_id,
            "langgraph_tool_failed",
            {
                "node": "tool_executor",
                "step": step,
                "tool": tool_name,
                "error_type": error.split(":", 1)[0],
            },
        )
        self.execution_store.save_checkpoint(
            request_id,
            step,
            {"graph_thread_id": request_id, "node": "tool_executor"},
        )
        return {"messages": messages, "tool_calls": tool_calls, "status": "running"}

    def _route_after_tool(self, state: GraphState) -> str:
        if state.get("status") in {"approval_required", "max_steps_reached"}:
            return "stop"
        return "continue"

    def _verifier_node(self, state: GraphState) -> GraphState:
        sources = [Source(**item) for item in state.get("sources", [])]
        status = state.get("status", "running")
        answer = state.get("answer") or "当前无法形成可靠回答。"
        if status in {"approval_required", "max_steps_reached"}:
            verification = {"passed": True, "skipped_for_status": status}
        else:
            answer, verification = verify_grounded_answer(
                answer, state.get("tool_calls", []), sources
            )
        request_id = state["request"]["request_id"]
        self.execution_store.append_event(
            request_id,
            "langgraph_node_completed",
            {
                "node": "output_verifier",
                "step": state.get("step", 0),
                "citation_passed": verification["passed"],
            },
        )
        return {
            "answer": answer,
            "citation_verification": verification,
            "status": status if status != "running" else "completed",
        }

    def _complete(
        self,
        request: AgentRequest,
        state: GraphState,
        recovered: bool,
    ) -> AgentResponse:
        sources = [Source(**item) for item in state.get("sources", [])]
        response = AgentResponse(
            answer=state.get("answer", "当前无法形成可靠回答。"),
            agent="v6_langgraph_agent",
            session_id=state["session_id"],
            sources=sources,
            tool_calls=state.get("tool_calls", []),
            metadata={
                "version": "v6",
                "runtime": "langgraph",
                "status": state.get("status", "completed"),
                "steps": state.get("step", 0),
                "recovered_from_checkpoint": recovered,
                "idempotent_replay": False,
                "compacted_messages": state.get("compacted_messages", 0),
                "artifacts": state.get("artifacts", []),
                "citation_verification": state.get("citation_verification", {}),
                "graph_thread_id": request.request_id,
                "frameworks": self.framework_versions(),
            },
        )
        self.conversation_store.record_turn(
            state["session_id"], request.text, response.answer
        )
        self.execution_store.complete(request.request_id, response.to_dict())
        self._audit(
            {
                "event": "langgraph_execution_completed",
                "request_id": request.request_id,
                "steps": state.get("step", 0),
                "tools": [call["name"] for call in state.get("tool_calls", [])],
            }
        )
        return response

    def get_events(self, request_id: str) -> list[dict[str, Any]]:
        return self.execution_store.get_events(request_id)

    def get_architecture(self) -> dict[str, Any]:
        return {
            "runtime": "langgraph",
            "nodes": self.GRAPH_NODES,
            "edges": [
                {"source": edge[0], "target": edge[1], "condition": edge[2]}
                if len(edge) == 3
                else {"source": edge[0], "target": edge[1]}
                for edge in self.GRAPH_EDGES
            ],
            "mermaid": self.graph.get_graph().draw_mermaid(),
            "frameworks": self.framework_versions(),
        }

    @staticmethod
    def framework_versions() -> dict[str, str]:
        names = ("langchain", "langgraph", "langchain-deepseek")
        return {name: importlib.metadata.version(name) for name in names}

    @staticmethod
    def _merge_source_dicts(
        existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        merged = list(existing)
        known = {item["source_id"] for item in merged}
        for item in incoming:
            if item["source_id"] not in known:
                merged.append(item)
                known.add(item["source_id"])
        return merged

    def _audit(self, event: dict[str, Any]) -> None:
        if self.audit_log:
            self.audit_log.write(event)
