import streamlit as st

from step_12_answer_generator import audit_citations, generate_answer
from step_15_registry_lookup import format_number, lookup_project


# 设置浏览器标签页标题与页面宽度。
st.set_page_config(
    page_title="碳信用披露证据助手",
    page_icon="🌿",
    layout="centered",
)


def display_text(value: object) -> str:
    """将空字段统一显示为“未披露”。"""
    return str(value) if value is not None else "未披露"


st.title("碳信用披露证据助手")
st.caption(
    "双语 PDF 证据问答与登记记录精确核对原型。"
    "结果仅供辅助审核，不构成合规、法律或绿洗判断。"
)

rag_tab, registry_tab = st.tabs(
    ["PDF 证据问答", "登记记录精确核对"]
)


with rag_tab:
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

    submitted = st.button(
        "检索并生成证据回答",
        type="primary",
        key="rag_submit",
    )

    if submitted:
        if not query.strip():
            st.warning("请先输入问题。")
        else:
            with st.spinner("正在检索、精排证据并生成回答，请稍候..."):
                try:
                    answer, sources = generate_answer(
                        query=query.strip(),
                        language=language_options[selected_language],
                        authority_level=authority_options[
                            selected_authority
                        ],
                    )
                    audit = audit_citations(answer, sources)

                    st.markdown("### 基于证据的回答")

                    if "证据不足，需要人工复核" in answer:
                        st.warning(answer)
                    else:
                        st.write(answer)

                    if audit["is_abstention"]:
                        st.info(
                            "引用校验：安全拒答。当前证据不足，"
                            "已提示人工复核。"
                        )
                    elif audit["is_valid"]:
                        citations = "、".join(
                            audit["cited_citations"]
                        )
                        st.success(
                            f"引用校验通过：回答引用了本轮有效证据 "
                            f"{citations}。"
                        )
                    else:
                        st.error(
                            "引用校验未通过：系统已将回答安全降级为人工复核。"
                        )

                    st.markdown("### 检索证据来源")
                    st.caption(
                        "以下为本次回答可使用的精排证据；"
                        "回答中的 [S编号] 对应其来源。"
                    )

                    for source in sources:
                        title = (
                            f"{source['citation']} "
                            f"{source['source_file']} "
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


with registry_tab:
    st.markdown("### 项目 ID 精确核对")
    st.caption(
        "此功能直接查询本地登记记录 Excel 的标准化副本；"
        "项目状态和信用数量不由大模型生成。"
    )

    project_id = st.text_input(
        "请输入 Project ID",
        placeholder="例如：ACR102",
    )

    registry_submitted = st.button(
        "查询登记记录",
        type="primary",
        key="registry_submit",
    )

    if registry_submitted:
        if not project_id.strip():
            st.warning("请先输入 Project ID。")
        else:
            with st.spinner("正在精确查询登记记录，请稍候..."):
                record = lookup_project(project_id)

            if record is None:
                st.warning(
                    f"未找到 Project ID：{project_id.strip()}。"
                    "这不代表项目不存在；请核对项目 ID、"
                    "数据版本或登记机构。"
                )
            else:
                st.success(
                    "已命中精确登记记录。以下字段直接来自本地 Excel，"
                    "未经过大模型推测。"
                )

                metric_issued, metric_retired, metric_remaining = st.columns(3)

                metric_issued.metric(
                    "已签发数量",
                    format_number(record["total_credits_issued"]),
                )
                metric_retired.metric(
                    "已注销数量",
                    format_number(record["total_credits_retired"]),
                )
                metric_remaining.metric(
                    "剩余数量",
                    format_number(record["total_credits_remaining"]),
                )

                st.markdown("#### 项目基本信息")
                st.write(f"**Project ID：** {display_text(record['project_id'])}")
                st.write(f"**项目名称：** {display_text(record['project_name'])}")
                st.write(f"**登记机构：** {display_text(record['registry'])}")
                st.write(
                    f"**项目状态：** "
                    f"{display_text(record['voluntary_status'])}"
                )
                st.write(
                    f"**项目类型：** "
                    f"{display_text(record['project_type'])}"
                )
                st.write(
                    f"**减排/移除：** "
                    f"{display_text(record['reduction_or_removal'])}"
                )
                st.write(
                    f"**国家/地区：** "
                    f"{display_text(record['country'])} / "
                    f"{display_text(record['state'])}"
                )
                st.write(
                    f"**项目开发方：** "
                    f"{display_text(record['project_developer'])}"
                )
                st.write(
                    f"**首次 Vintage 年份：** "
                    f"{display_text(record['first_vintage_year'])}"
                )

                st.markdown("#### 结构化数据来源")
                st.caption(
                    f"工作簿：{record['source_workbook']} ｜ "
                    f"工作表：{record['source_sheet']} ｜ "
                    f"Excel 行号：{record['source_excel_row']}"
                )


st.divider()

st.markdown(
    """
    **系统边界**

    - PDF 问答仅依据已导入的静态 PDF 资料回答，并显示文件名与页码；
    - 登记记录核对仅依据本地 Excel 快照，不代表实时登记机构数据；
    - 资料不足或未找到项目 ID 时，系统提示人工复核；
    - 不对企业是否存在绿洗、违法或合规风险作出自动结论。
    """
)