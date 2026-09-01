"""Visual V6 console for runtime comparison, graph inspection, and execution."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .bootstrap import create_default_orchestrator
from .contracts import AgentRequest


PROJECT_URL = "https://github.com/hhhttyzuishuai/carbon-credit-evidence-rag"
ROOT = Path(__file__).resolve().parents[2]
COMPARISON_PATH = ROOT / "data" / "eval" / "v6_runtime_comparison.json"


def _comparison_data() -> dict:
    if COMPARISON_PATH.exists():
        return json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
    return {"comparison": [], "scope": "Comparison file not found."}


def _graph_dot() -> str:
    return """
digraph AgentV6 {
  rankdir=LR;
  bgcolor="transparent";
  node [shape=box style="rounded,filled" fontname="Arial" color="#20c997"
        fillcolor="#102d3d" fontcolor="white" margin="0.20,0.12"];
  edge [color="#55cfc0" fontname="Arial" fontcolor="#385b63"];
  start [label="START" shape=circle fillcolor="#17394a"];
  planner [label="Planner\nLangChain + DeepSeek"];
  tool [label="Tool Executor\nStructuredTool"];
  verifier [label="Output Verifier\nCitation + Policy" color="#38bdf8"];
  end [label="END" shape=doublecircle fillcolor="#17394a"];
  start -> planner;
  planner -> tool [label=" tool call"];
  tool -> planner [label=" observation"];
  planner -> verifier [label=" final"];
  tool -> verifier [label=" stop / approval"];
  verifier -> end;
}
"""


def _apply_style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp {background: linear-gradient(145deg,#f5faf9 0%,#eef5f7 100%);}
        [data-testid="stSidebar"] {background:#071b28;}
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p {color:#e8f6f5;}
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] [data-baseweb="select"] * {
          color:#15353d !important;-webkit-text-fill-color:#15353d !important;
          opacity:1 !important;
        }
        [data-testid="stSidebar"] button *,
        [data-testid="stSidebar"] a * {
          color:#123b41 !important;-webkit-text-fill-color:#123b41 !important;
          opacity:1 !important;
        }
        .hero {padding:1.3rem 1.6rem;border-radius:18px;background:linear-gradient(115deg,#071b28,#12444a);color:white;margin-bottom:1rem;box-shadow:0 10px 32px rgba(15,49,62,.18)}
        .hero h1 {margin:0 0 .35rem 0;font-size:2.05rem;}
        .hero p {margin:0;color:#b9d9dc;}
        .metric-card {background:white;border:1px solid #dce9e9;border-radius:14px;padding:1rem 1.1rem;box-shadow:0 4px 16px rgba(27,65,74,.06);min-height:102px;}
        .metric-card .value {font-size:1.55rem;font-weight:750;color:#0b4f50;}
        .metric-card .label {font-size:.83rem;color:#58747c;margin-top:.25rem;}
        .runtime-pill {display:inline-block;background:#daf5ed;color:#12614f;padding:.25rem .65rem;border-radius:999px;font-size:.78rem;font-weight:700;}
        div[data-testid="stTabs"] button {font-weight:650;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _metric_card(st, value: str, label: str) -> None:
    st.markdown(
        f'<div class="metric-card"><div class="value">{value}</div>'
        f'<div class="label">{label}</div></div>',
        unsafe_allow_html=True,
    )


def main() -> None:
    try:
        import pandas as pd
        import streamlit as st
    except ImportError as error:
        raise RuntimeError("启动界面需要安装 streamlit 和 pandas。") from error

    st.set_page_config(
        page_title="Carbon Credit Agent V6",
        page_icon="◈",
        layout="wide",
    )
    _apply_style(st)

    @st.cache_resource(show_spinner=False)
    def load_runtime(runtime_kind: str):
        return create_default_orchestrator(
            runtime_directory="runtime", runtime_kind=runtime_kind
        )

    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid4().hex
    if "request_id" not in st.session_state:
        st.session_state.request_id = uuid4().hex

    with st.sidebar:
        st.markdown("## ◈ Agent Control")
        runtime_label = st.radio(
            "运行时",
            ["V6 · LangGraph", "V5 · Custom Harness"],
            help="两套运行时共用同一组知识库和业务工具。",
        )
        runtime_kind = "langgraph" if runtime_label.startswith("V6") else "custom"
        intent = st.selectbox(
            "任务意图",
            ["auto", "chat", "knowledge", "registry", "risk_review"],
        )
        approval = st.checkbox("授权实验性风险审核")
        st.text_input("Request ID", key="request_id")
        st.caption(f"Session · {st.session_state.session_id[:12]}")
        if st.button("生成新的 Request ID", width="stretch"):
            st.session_state.request_id = uuid4().hex
            st.rerun()
        st.markdown("---")
        st.link_button("查看 GitHub 项目", PROJECT_URL, width="stretch")

    st.markdown(
        """
        <div class="hero">
          <span class="runtime-pill">OPEN SOURCE · V6.1</span>
          <h1>Carbon Credit Evidence Agent</h1>
          <p>LangGraph 状态编排 · LangChain 工具接口 · 双语证据检索 · 可恢复执行</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cards = st.columns(4)
    with cards[0]:
        _metric_card(st, "2,572", "双语知识块")
    with cards[1]:
        _metric_card(st, "11,110", "登记记录")
    with cards[2]:
        _metric_card(st, "0.863", "Reranker MRR")
    with cards[3]:
        _metric_card(st, "42", "离线测试")

    console_tab, graph_tab, compare_tab, evidence_tab = st.tabs(
        ["Agent 控制台", "执行图", "V5 / V6 对比", "评测与证据"]
    )

    with console_tab:
        st.markdown(f"### 当前运行时：{runtime_label}")
        st.caption(
            "运行真实问题需要配置 DEEPSEEK_API_KEY；知识检索还需要本地索引和模型。"
        )
        question = st.text_area(
            "输入审核问题",
            placeholder="例如：Article 6.2 对 cooperative approaches 有哪些要求？",
            height=120,
        )
        project_id = st.text_input("Project ID（登记查询时可填）")
        if st.button(
            "运行 Agent",
            type="primary",
            disabled=not question.strip(),
            width="stretch",
        ):
            payload = {"project_id": project_id} if project_id else {}
            runtime = load_runtime(runtime_kind)
            with st.spinner("正在执行状态图与工具调用……"):
                response = runtime.handle(
                    AgentRequest(
                        text=question,
                        session_id=st.session_state.session_id,
                        intent=intent,
                        payload=payload,
                        approval_granted=approval,
                        request_id=st.session_state.request_id,
                    )
                )
            st.session_state.last_response = response.to_dict()
            st.session_state.last_events = runtime.get_events(
                st.session_state.request_id
            )

        if "last_response" in st.session_state:
            response = st.session_state.last_response
            st.markdown("#### 回答")
            st.info(response["answer"])
            summary = st.columns(3)
            summary[0].metric("Agent", response["agent"])
            summary[1].metric("工具调用", len(response["tool_calls"]))
            summary[2].metric("来源", len(response["sources"]))
            left, right = st.columns([1, 1])
            with left:
                st.markdown("#### 来源")
                st.dataframe(response["sources"], width="stretch")
            with right:
                st.markdown("#### 工具轨迹")
                st.dataframe(response["tool_calls"], width="stretch")
            with st.expander("执行事件与运行元数据", expanded=True):
                st.json(st.session_state.get("last_events", []))
                st.json(response["metadata"])

    with graph_tab:
        st.markdown("### V6 状态图")
        st.graphviz_chart(_graph_dot(), width="stretch")
        st.caption(
            "Planner 只负责选择工具或结束；工具节点执行 Schema 校验和审批；"
            "Verifier 统一检查引用与输出边界。"
        )
        node_columns = st.columns(3)
        node_columns[0].info("**Planner**\n\nChatDeepSeek + StructuredTool Schema")
        node_columns[1].info("**Tool Executor**\n\nKnowledge / Registry / Risk Review")
        node_columns[2].info("**Output Verifier**\n\nSource ID + Policy Check")

    with compare_tab:
        comparison = _comparison_data()
        st.markdown("### 同一回归集下的双运行时")
        rows = comparison.get("comparison", [])
        if rows:
            frame = pd.DataFrame(rows).set_index("runtime")
            display_frame = frame.rename(
                columns={
                    "cases": "案例数",
                    "tool_selection_accuracy": "工具选择准确率",
                    "task_completion_rate": "任务完成率",
                    "average_steps": "平均步数",
                    "median_local_latency_ms": "本地中位耗时(ms)",
                    "checkpoint_recovery_rate": "检查点恢复率",
                }
            )
            st.dataframe(display_frame, width="stretch")
            chart = frame[
                [
                    "tool_selection_accuracy",
                    "task_completion_rate",
                    "checkpoint_recovery_rate",
                ]
            ]
            st.bar_chart(
                chart.T,
                height=320,
                stack=False,
                color=["#20c997", "#38bdf8"],
            )
            latency = frame[["median_local_latency_ms"]]
            st.bar_chart(
                latency.T,
                height=240,
                stack=False,
                color=["#20c997", "#38bdf8"],
            )
        st.warning(
            comparison.get("scope", ""),
            icon="⚠️",
        )
        st.markdown(
            """
            | 对比项 | V5 Custom Harness | V6 LangGraph |
            |---|---|---|
            | 编排方式 | 手写循环与状态恢复 | StateGraph 条件节点 |
            | 工具接口 | 自定义 ToolSpec | LangChain StructuredTool |
            | 检查点 | 自建 SQLite Store | LangGraph Checkpointer |
            | 优势 | 机制透明、依赖少 | 生态标准、图可视化、便于扩展 |
            """
        )

    with evidence_tab:
        st.markdown("### 可复核的项目指标")
        retrieval = pd.DataFrame(
            [
                {"method": "Dense", "Hit@1": 0.54, "Hit@3": 0.72, "MRR": 0.656},
                {"method": "BM25", "Hit@1": 0.68, "Hit@3": 0.88, "MRR": 0.785},
                {"method": "RRF Hybrid", "Hit@1": 0.58, "Hit@3": 0.82, "MRR": 0.722},
                {"method": "Cross-Encoder", "Hit@1": 0.78, "Hit@3": 0.98, "MRR": 0.863},
            ]
        ).set_index("method")
        st.bar_chart(retrieval, height=330)
        st.dataframe(retrieval, width="stretch")
        st.caption(
            "检索指标来自50条人工标注问题；Agent对比来自12条确定性离线回归，"
            "两者都不代表开放域或线上流量表现。"
        )
        st.markdown(
            f"完整源码、版本标签和复现实验：[GitHub Repository]({PROJECT_URL})"
        )


if __name__ == "__main__":
    main()
