# Carbon Credit Evidence Review Agent

[![Agent Tests](https://github.com/hhhttyzuishuai/carbon-credit-evidence-rag/actions/workflows/agent-tests.yml/badge.svg)](https://github.com/hhhttyzuishuai/carbon-credit-evidence-rag/actions/workflows/agent-tests.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2.11-20c997)
![LangChain](https://img.shields.io/badge/LangChain-1.3.18-1C3C3C)

面向碳信用披露审核的可追溯 Agent 系统。Agent 可以根据问题选择本地知识检索、
项目登记查询或实验性风险审核工具，并在输出前检查证据引用和业务边界。项目同时
保留 V5 自研 Harness 与 V6 LangGraph Runtime，用同一套测试和业务工具比较两种
编排方式。

> 这是作品集级工程原型，不是生产系统，也不替代法律、合规、审计或绿洗判断。

![V6 architecture](docs/assets/agent-v6-architecture.svg)

## 项目入口

- GitHub：<https://github.com/hhhttyzuishuai/carbon-credit-evidence-rag>
- 可视化控制台：`streamlit run src/step_13_streamlit_app.py`
- API 文档：启动服务后访问 `http://127.0.0.1:8000/docs`
- 简历版本对比：[docs/V5_V6_RESUME_COMPARISON.md](docs/V5_V6_RESUME_COMPARISON.md)
- 完整项目报告：[docs/AGENT_PROJECT_REPORT.md](docs/AGENT_PROJECT_REPORT.md)

## 版本演进

| 版本 | 能力 | Git 标签 |
|---|---|---|
| V1 | 无状态问答与可替换 LLM Gateway | `agent-v1.0.0` |
| V2 | SQLite 多轮记忆、原子 Turn、有限历史窗口 | `agent-v2.0.0` |
| V3 | Hybrid + Reranker 知识库、页码来源、引用审计 | `agent-v3.0.0` |
| V4 | 确定性多 Agent 路由、业务工具、审批和 FastAPI | `agent-v4.0.0` |
| V5 | 自研 Agent Loop、Tool Registry、幂等、检查点和 MCP | `agent-v5.0.0` |
| V6 | LangGraph StateGraph、LangChain Tools、双运行时与可视化 | `agent-v6.0.0` |

每个版本的设计与边界保存在 [docs/releases](docs/releases)。

## V5 与 V6 的区别

| 对比项 | V5 Custom Harness | V6 LangGraph |
|---|---|---|
| 模型接口 | OpenAI-compatible 自定义 Planner | 官方 `ChatDeepSeek` 集成 |
| 工具接口 | 自定义 `ToolSpec` | LangChain `StructuredTool` |
| 编排方式 | 手写受限循环 | `StateGraph` 节点与条件边 |
| 检查点 | 自建 SQLite Execution Store | LangGraph Checkpointer + 幂等账本 |
| 可观察性 | 自定义事件记录 | 节点事件、Graph Introspection、事件重放 |
| 适用价值 | 机制透明、便于理解底层 | 生态标准、便于增加节点和子图 |

两版共用 Knowledge、Registry、Risk Review、引用校验和审批策略，因此比较的是
编排层，而不是换一套数据制造指标差异。默认运行时为 V6，可用
`--runtime custom` 切回 V5。

## 核心能力

- LangGraph 节点：`planner → tool_executor → output_verifier`，通过条件边循环；
- LangChain `StructuredTool` 统一工具参数 Schema，DeepSeek 返回标准 Tool Call；
- 最多执行6步，支持工具重试、敏感工具审批和异常停止；
- Request ID 幂等：完成请求直接重放，同 ID 不同内容拒绝执行；
- LangGraph Checkpointer 与 SQLite 事件账本支持失败节点恢复；
- 多轮历史超限后压缩，大工具结果按 SHA-256 外置；
- 知识与登记回答必须引用本轮 `[S编号]` 或 `[T编号]`；
- CLI、FastAPI、Streamlit 和只读 MCP 使用同一套业务工具；
- JSONL 审计日志递归脱敏，不记录隐藏思维链。

## 数据与评测

知识库包含 9 份静态中英文 PDF，共 797 页、2,572 个文本块。50 条人工标注
问题以来源文件和物理页码作为相关性标准。

| 方法 | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Dense Retrieval | 0.540 | 0.720 | 0.656 |
| BM25 | 0.680 | 0.880 | 0.785 |
| RRF Hybrid Retrieval | 0.580 | 0.820 | 0.722 |
| Cross-Encoder Reranker | **0.780** | **0.980** | **0.863** |

Agent 离线验收：

- 42 个单元、API 与集成测试；
- V4 固定路由回归：24/24；
- V5 与 V6 在同一12条任务上均为工具选择 12/12、完成 12/12；
- 两版平均执行步数均为1.833，故障注入恢复均为4/4；
- 当前一次本地 Fake Tool 回归中，V5中位编排耗时88.37 ms，V6为123.68 ms。

最后一项只测本机 SQLite 和框架编排开销，不包含真实 LLM、网络或 GPU 检索，
不能解释为 V5 的实际业务性能优于 V6。固定回归集也不代表开放域泛化能力。

## 可视化控制台

Streamlit 页面不只是聊天框，还包含：

- V5/V6 运行时切换；
- LangGraph 节点与条件边可视化；
- 工具轨迹、来源和执行事件；
- 双运行时指标对比；
- Dense、BM25、RRF、Cross-Encoder 检索指标图。

```powershell
& .\.venv\Scripts\python.exe -m streamlit run src\step_13_streamlit_app.py
```

页面不依赖 API Key 即可查看架构和离线指标；执行真实问题需要配置 DeepSeek，
知识问答还需要本地索引与模型。

## 本地运行

推荐在 PyCharm 中新建 Python 3.10 虚拟环境：

```powershell
py -3.10 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH="src"
```

复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`。V6 使用
`langchain-deepseek` 的 `ChatDeepSeek(model="deepseek-chat")`；API Key、原始
数据、索引、模型和运行日志不会提交 Git。

### CLI

```powershell
# V6 LangGraph（默认）
& .\.venv\Scripts\python.exe -m carbon_agent.cli run `
  "Article 6.2 有哪些要求？请给本地证据" --runtime langgraph

# V5 自研 Harness
& .\.venv\Scripts\python.exe -m carbon_agent.cli run `
  "Article 6.2 有哪些要求？请给本地证据" --runtime custom
```

### FastAPI

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli serve `
  --runtime langgraph --port 8000
```

接口包括：

- `GET /health`
- `POST /v1/agent/chat`
- `GET /v1/executions/{request_id}/events`
- `GET /v1/architecture`

### MCP Server

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli mcp-server
```

MCP stdio Server 只暴露 `knowledge_search` 与 `registry_lookup`，不会暴露实验性
风险审核工具。

### 测试与评测

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe scripts\evaluate_agent_routes.py
& .\.venv\Scripts\python.exe scripts\evaluate_v5_harness.py
& .\.venv\Scripts\python.exe scripts\evaluate_v6_runtime_comparison.py
```

## 安全与工程边界

- 登记记录来自 `v2026-02` 静态 Excel 快照，不代表登记机构实时状态；
- 风险模型验证数据有限，只能作为实验性审核信号；
- 当前 SQLite Checkpointer 适合单机作品集，不等于生产级分布式持久化；
- 未接入企业 SSO/RBAC、租户隔离、KMS、队列、限流、OpenTelemetry 和真实压测；
- 系统不会自动输出企业绿洗、违法或合规结论。

## 项目结构

```text
src/carbon_agent/
  harness.py             # V5 自研运行时
  langgraph_runtime.py   # V6 StateGraph 运行时
  langchain_adapter.py   # ChatDeepSeek 与 StructuredTool
  tooling.py             # 共用业务工具与权限
  streamlit_app.py       # 可视化控制台
tests/                   # 42 个离线测试
data/eval/               # 检索、路由、Harness 与双运行时评测
scripts/                 # 可复现评测脚本
docs/releases/           # V1-V6 版本留档
```
