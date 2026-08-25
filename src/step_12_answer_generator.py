import argparse
import os

from dotenv import load_dotenv
from openai import OpenAI

from step_09_hybrid_retriever import hybrid_search


# 生成模型：速度和成本更适合当前 RAG 原型。
MODEL_NAME = "deepseek-v4-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


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


def format_context(results: list[dict]) -> tuple[str, list[str]]:
    """把检索结果转换为大模型可读的带编号证据文本。"""
    sections = []
    source_lines = []

    for index, result in enumerate(results, start=1):
        chunk = result["chunk"]
        source_label = (
            f"[S{index}] {chunk['source_file']}，"
            f"第 {chunk['page_number']} 页，"
            f"{chunk['document_type']}"
        )

        sections.append(
            f"{source_label}\n"
            f"{chunk['text']}"
        )
        source_lines.append(source_label)

    return "\n\n".join(sections), source_lines


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
) -> tuple[str, list[str]]:
    """执行 Hybrid 检索，并基于证据生成带引用的回答。"""

    # 当前评估中 Hybrid 表现最好，因此作为 V1 生成层的默认检索器。
    results = hybrid_search(
        query=query,
        top_k=top_k,
        candidate_k=20,
        language=language,
        document_type=document_type,
        authority_level=authority_level,
    )

    if not results:
        return "证据不足，需要人工复核。", []

    context, source_lines = format_context(results)
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

    answer = response.choices[0].message.content
    return answer or "证据不足，需要人工复核。", source_lines


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
        print(source)


if __name__ == "__main__":
    main()