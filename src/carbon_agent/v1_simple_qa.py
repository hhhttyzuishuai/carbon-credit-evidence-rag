"""V1: stateless question-answering agent."""

from __future__ import annotations

from .contracts import AgentResponse, Message
from .llm import ChatGateway


V1_SYSTEM_PROMPT = """你是一个可靠、简洁的通用问答助手。
如果问题缺少关键信息，请说明不确定性并提出一个最必要的澄清问题。
不要声称调用了工具、查询了数据库或读取了资料，除非上下文确实提供了这些结果。
使用与用户相同的语言回答。"""


class SimpleQAAgent:
    name = "simple_qa_agent"

    def __init__(self, gateway: ChatGateway) -> None:
        self.gateway = gateway

    def answer(self, question: str) -> AgentResponse:
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("问题不能为空。")

        messages = [
            Message(role="system", content=V1_SYSTEM_PROMPT),
            Message(role="user", content=cleaned_question),
        ]
        answer = self.gateway.complete(messages).strip()
        if not answer:
            raise RuntimeError("模型返回了空回答。")

        return AgentResponse(
            answer=answer,
            agent=self.name,
            metadata={"version": "v1", "memory_enabled": False},
        )

