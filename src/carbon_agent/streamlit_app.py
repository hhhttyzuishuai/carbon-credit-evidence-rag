"""Unified Streamlit console backed by the same V5 harness as API and CLI."""

from __future__ import annotations

from uuid import uuid4

from .bootstrap import create_default_orchestrator
from .contracts import AgentRequest


def main() -> None:
    try:
        import streamlit as st
    except ImportError as error:
        raise RuntimeError("启动界面需要安装 streamlit。") from error

    st.set_page_config(page_title="Carbon Credit Agent V5", layout="wide")
    st.title("Carbon Credit Agent V5")
    st.caption("Agent Harness · 工具选择 · 可恢复执行 · 引用校验 · 人工审批")

    if "runtime" not in st.session_state:
        st.session_state.runtime = create_default_orchestrator()
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid4().hex

    with st.sidebar:
        st.subheader("执行控制")
        intent = st.selectbox(
            "期望意图",
            ["auto", "chat", "knowledge", "registry", "risk_review"],
        )
        approval = st.checkbox("允许执行实验性风险审核工具")
        request_id = st.text_input("Request ID", value=uuid4().hex)
        st.code(f"Session: {st.session_state.session_id}")

    question = st.text_area("问题", height=110)
    project_id = st.text_input("Project ID（可选）")
    if st.button("运行 Agent", type="primary", disabled=not question.strip()):
        payload = {"project_id": project_id} if project_id else {}
        with st.spinner("Agent 正在规划和调用工具……"):
            response = st.session_state.runtime.handle(
                AgentRequest(
                    text=question,
                    session_id=st.session_state.session_id,
                    intent=intent,
                    payload=payload,
                    approval_granted=approval,
                    request_id=request_id,
                )
            )
        st.subheader("回答")
        st.write(response.answer)
        left, right = st.columns(2)
        with left:
            st.subheader("来源")
            st.json([source.__dict__ for source in response.sources])
        with right:
            st.subheader("工具轨迹")
            st.json(response.tool_calls)
        st.subheader("运行元数据")
        st.json(response.metadata)
        with st.expander("可重放事件"):
            st.json(st.session_state.runtime.get_events(request_id))


if __name__ == "__main__":
    main()
