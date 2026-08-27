# Agent V3：知识库与引用审计

## 版本目标

将原项目中经过评测的双语 RAG 链路接入 Agent，同时严格区分“对话历史”和“本轮可引用证据”。

## 本次交付

- `KnowledgeRetriever` 协议定义知识源边界；
- `ExistingRAGRetriever` 复用原有 Hybrid top-20 与 Cross-Encoder top-k；
- `KnowledgeAgent` 支持知识库、多轮会话和结构化来源返回；
- 证据保留文件名、物理页码、文档类型、语言和精排分数；
- 引用审计拒绝不存在的 `[S编号]`，正常答案无引用时同样安全降级；
- 检索为空时不调用大模型，直接返回人工复核；
- 离线测试覆盖有效引用、伪造引用、空检索和历史/证据隔离。

## 运行与验收

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
python -m carbon_agent.cli knowledge "CCER 项目登记需要提交什么材料？"
```

真实知识库运行依赖本地 `data/processed`、`data/index`、Embedding 与 Reranker 模型，以及有效的 DeepSeek API Key；这些大文件按现有安全策略不提交到 Git。

## 知识点

- Adapter 模式让 Agent 复用既有检索链路，而不重写经过评测的 RAG；
- Retrieval Grounding 要验证“回答引用了什么”，不能只把文本塞进 Prompt；
- 历史对话帮助理解指代，但不能升级为事实证据；
- 无证据、无引用、越界引用分别进入可解释的安全降级路径。

## 当前边界

本版本尚未加入业务意图路由和工具调用。下一版本将拆分路由、知识、登记核对、风险审核与结果校验等职责，并增加审计日志和高风险工具策略。
