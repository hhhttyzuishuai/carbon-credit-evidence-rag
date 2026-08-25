import streamlit as st
from step_12_answer_generator import audit_citations, generate_answer

# 设置浏览器标签页标题与页面宽度。
st.set_page_config(
    page_title="碳信用披露证据助手",
    page_icon="🌿",
    layout="centered",
)

st.title("碳信用披露证据助手")
st.caption("基于本地 PDF 证据的双语 RAG 原型。回答仅供辅助审核，不构成企业绿洗或合规判断。")

st.markdown("### 检索范围")

# 将页面中的中文选项映射为后端检索器需要的参数。
language_options = {
    "自动识别": None,
    "中文资料": "zh",
    "英文资料": "en",
}

authority_options = {
    "全部资料": None,
    "仅官方规则": "official",
    "仅企业披露": "company_disclosure",
    "仅企业意见材料": "company_opinion",
}

selected_language = st.selectbox(
    "资料语言",
    options=list(language_options),
)

selected_authority = st.selectbox(
    "资料类型",
    options=list(authority_options),
)

st.markdown("### 提问")

query = st.text_area(
    "请输入问题",
    placeholder="例如：温室气体自愿减排项目申请登记需要具备哪些条件？",
    height=120,
)

submitted = st.button("检索并生成证据回答", type="primary")

if submitted:
    if not query.strip():
        st.warning("请先输入问题。")
    else:
        with st.spinner("正在检索证据并生成回答，请稍候..."):
            try:
                answer, sources = generate_answer(
                    query=query.strip(),
                    language=language_options[selected_language],
                    authority_level=authority_options[selected_authority],
                )
                audit = audit_citations(answer, sources)

                st.markdown("### 基于证据的回答")

                if "证据不足，需要人工复核" in answer:
                    st.warning(answer)
                else:
                    st.write(answer)

                if audit["is_abstention"]:
                    st.info("引用校验：安全拒答。当前证据不足，已提示人工复核。")
                elif audit["is_valid"]:
                    citations = "、".join(audit["cited_citations"])
                    st.success(f"引用校验通过：回答引用了本轮有效证据 {citations}。")
                else:
                    st.error("引用校验未通过：系统已将回答安全降级为人工复核。")

                st.markdown("### 检索证据来源")
                st.caption("以下为本次回答可使用的候选证据；回答中的 [S编号] 对应其来源。")

                for source in sources:
                    title = (
                        f"{source['citation']} {source['source_file']} "
                        f"· 第 {source['page_number']} 页"
                    )

                    with st.expander(title):
                        st.caption(
                            f"文档类型：{source['document_type']} ｜ "
                            f"语言：{source['language']}"
                        )
                        st.write(source["text_preview"])

            except Exception as error:
                st.error(
                    "生成失败。请检查网络、DeepSeek 账户余额、"
                    "本地 .env 配置，以及终端中的错误信息。"
                )
                st.exception(error)

st.divider()

st.markdown(
    """
    **系统边界**

    - 仅依据已导入的 PDF 资料回答；
    - 会显示文件名与提取页码；
    - 资料不足时提示“证据不足，需要人工复核”；
    - 不对企业是否存在绿洗或违法行为作出结论。
    """
)