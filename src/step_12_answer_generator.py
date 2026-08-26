import argparse
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from step_09_hybrid_retriever import hybrid_search
from step_10_reranker import rerank


# 生成模型：速度和成本更适合当前 RAG 原型。
MODEL_NAME = "deepseek-v4-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 统一的安全拒答语句。
ABSTENTION_MESSAGE = "证据不足，需要人工复核。"

# 匹配回答中的 [S1]、[S2] 等来源引用。
CITATION_PATTERN = re.compile(r"\[S(\d+)\]")


SYSTEM_PROMPT = """
你是“碳信用披露证据助手”。

只能依据用户提供的证据回答，不能使用外部知识或自行补充事实。

规则：
1. 每个关键结论后必须使用 [S1]、[S2] 等形式引用证据。
2. 不得编造文件名、页码、数字、法规要求或企业事实。
3. 如果证据无法回答问题，必须明确回答：
   “证据不足，需要人工复核。”
4. 不得判断任何企业是否存在“绿洗”或违法行为。
5. 使用与用户问题相同的语言回答。
6. 回答简洁，优先使用 1—3 段。
"""


def format_context(results: list[dict]) -> tuple[str, list[dict]]:
    """把检索结果转换为模型上下文，并保留界面展示所需的来源信息。"""
    sections = []
    source_records = []

    for index, result in enumerate(results, start=1):
        chunk = result["chunk"]
        citation = f"[S{index}]"

        source_label = (
            f"{citation} {chunk['source_file']}，"
            f"第 {chunk['page_number']} 页，"
            f"{chunk['document_type']}"
        )

        sections.append(
            f"{source_label}\n"
            f"{chunk['text']}"
        )

        # 保持与发送给大模型的证据顺序一致，确保 [S编号] 可追溯。
        source_records.append(
            {
                "citation": citation,
                "source_file": chunk["source_file"],
                "page_number": chunk["page_number"],
                "document_type": chunk["document_type"],
                "language": chunk["language"],
                "text_preview": chunk["text"][:500],
            }
        )

    return "\n\n".join(sections), source_records


def audit_citations(answer: str, sources: list[dict]) -> dict:
    """检查回答是否只引用了本轮真实存在的证据编号。"""
    valid_citations = {
        source["citation"]
        for source in sources
    }

    cited_citations = list(
        dict.fromkeys(
            f"[S{number}]"
            for number in CITATION_PATTERN.findall(answer)
        )
    )

    invalid_citations = [
        citation
        for citation in cited_citations
        if citation not in valid_citations
    ]

    is_abstention = ABSTENTION_MESSAGE in answer
    is_valid = (
        not invalid_citations
        and (is_abstention or bool(cited_citations))
    )

    return {
        "is_valid": is_valid,
        "is_abstention": is_abstention,
        "cited_citations": cited_citations,
        "invalid_citations": invalid_citations,
    }


def build_client() -> OpenAI:
    """从本地 .env 读取密钥，并创建 DeepSeek 客户端。"""
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未检测到 DEEPSEEK_API_KEY，请检查项目根目录的 .env 文件。"
        )

    return OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
    )


def generate_answer(
    query: str,
    top_k: int = 5,
    language: str | None = None,
    document_type: str | None = None,
    authority_level: str | None = None,
) -> tuple[str, list[dict]]:
    """执行 Hybrid 召回、Cross-Encoder 精排，并基于证据生成回答。"""

    # 先快速召回 20 条候选；该配置在 50 条评估集上优于候选数 50。
    candidates = hybrid_search(
        query=query,
        top_k=20,
        candidate_k=20,
        language=language,
        document_type=document_type,
        authority_level=authority_level,
    )

    # 再通过Cross-Encoder精排，只将钱top_k条证据交给大模型
    results = rerank(
        query=query,
        candidates=candidates,
        top_k=top_k,
    )

    if not results:
        return ABSTENTION_MESSAGE, []

    context, source_records = format_context(results)
    client = build_client()

    user_prompt = (
        f"用户问题：{query}\n\n"
        f"以下是仅可使用的证据：\n\n{context}\n\n"
        "请仅依据上述证据回答，并在关键结论后标注 [S编号]。"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=600,
    )

    answer = response.choices[0].message.content or ABSTENTION_MESSAGE
    audit = audit_citations(answer, source_records)

    # 正常回答若无引用，或引用了本轮不存在的编号，则安全降级。
    if not audit["is_valid"]:
        return ABSTENTION_MESSAGE, source_records

    return answer, source_records


def main() -> None:
    """命令行入口：问题 → Hybrid 检索 → DeepSeek 证据回答。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--language", choices=["zh", "en"])
    parser.add_argument(
        "--document-type",
        choices=[
            "official_rule",
            "official_market_report",
            "company_disclosure",
            "comment_letter",
        ],
    )
    parser.add_argument(
        "--authority-level",
        choices=[
            "official",
            "company_disclosure",
            "company_opinion",
        ],
    )
    args = parser.parse_args()

    answer, sources = generate_answer(
        query=args.query,
        top_k=args.top_k,
        language=args.language,
        document_type=args.document_type,
        authority_level=args.authority_level,
    )

    print(f"\n查询：{args.query}")
    print(f"生成模型：{MODEL_NAME}")
    print("\n=== 基于证据的回答 ===")
    print(answer)

    print("\n=== 检索证据来源 ===")
    for source in sources:
        print(
            f"{source['citation']} {source['source_file']}，"
            f"第 {source['page_number']} 页，"
            f"{source['document_type']}"
        )


if __name__ == "__main__":
    main()