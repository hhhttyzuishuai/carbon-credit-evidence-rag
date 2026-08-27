# Carbon Credit Evidence Review Agent

面向碳信用披露审核的可追溯 Agent Harness。项目从双语 RAG 逐版演进到
模型驱动的工具循环，把多轮记忆、PDF 证据检索、登记记录查询和受控风险审核
统一到可恢复、可重放、可审计的运行时。

> 这是作品集级“伪企业级”工程原型，不是生产系统，也不替代法律、合规、
> 审计或绿洗判断。

## 版本演进

| 版本 | 能力 | Git 标签 |
|---|---|---|
| V1 | 无状态简单问答、可替换 LLM Gateway | `agent-v1.0.0` |
| V2 | SQLite 多轮记忆、原子 Turn、有限历史窗口 | `agent-v2.0.0` |
| V3 | Hybrid + Reranker 知识库、页码来源、引用审计 | `agent-v3.0.0` |
| V4 | 确定性多 Agent 路由、登记/风险工具、授权、FastAPI | `agent-v4.0.0` |
| V5 | 模型驱动 Agent Loop、Tool Registry、幂等/检查点/重放、MCP | `agent-v5.0.0` |

每个大版本的目标、验收和当时边界保存在 [docs/releases](docs/releases)。完整
复盘及简历写法见 [Agent 项目报告](docs/AGENT_PROJECT_REPORT.md)。

## V5 架构

```text
CLI / FastAPI / Streamlit / MCP Client
                 |
                 v
          AgentHarness (max 6 steps)
                 |
      observe -> ToolPlanner -> decide
          ^          |           |
          |          |       final answer
          |          v           |
          +---- ToolRegistry -----+
                 |    |    |
                 v    v    v
              PDF   Registry  Experimental
              RAG   Snapshot   Risk Review
                 |
        citation + policy verifier
                 |
       AgentResponse + Sources + Events

SQLite: conversation memory / execution checkpoints / idempotency
Files:  SHA-256 large-output artifacts / redacted JSONL audit
```

V4 仍保留为可比较的确定性多 Agent 实现；V5 默认运行时不再由关键词 Router
直接决定路线，而是让模型在每一步选择工具或结束。循环有最大步数、参数 Schema、
重试预算、人工审批和输出校验，不能无限自主执行。

## 核心工程能力

- `ToolRegistry` 为 Knowledge、Registry、Risk Review 提供统一 JSON Schema、
  参数校验、权限标记和重试策略；
- `AgentHarness` 实现 `observe -> decide -> tool -> observe` 循环，最多 6 步；
- Request ID 与请求指纹保证幂等；同 ID 不同内容会被拒绝，已完成请求直接返回
  原结果；
- 每次工具执行后写 SQLite 检查点和事件；失败后使用同一 Request ID 可继续；
- 上下文超限时确定性压缩旧消息，大工具输出按 SHA-256 外置到 Artifact；
- 知识/登记回答只能引用本轮 `[S编号]` / `[T编号]`，引用缺失或越界会降级；
- 风险审核要求显式授权，MCP Server 只暴露只读知识检索与登记查询；
- CLI、FastAPI 和 Streamlit 使用同一个 Runtime，API 提供执行事件查询；
- JSONL 审计递归脱敏 Key、Token、Secret、Password，不记录隐藏思维链。

## 原 RAG 数据与评测

语料为 9 份静态中英文 PDF，共 797 页、2,572 个 Chunks。50 条人工标注
问题以来源文件和物理页码为相关性标准。

| 方法 | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Dense Retrieval | 0.540 | 0.720 | 0.656 |
| BM25 | 0.680 | 0.880 | 0.785 |
| RRF Hybrid Retrieval | 0.580 | 0.820 | 0.722 |
| Cross-Encoder Reranker | **0.780** | **0.980** | **0.863** |

这些结果只适用于当前静态语料和 50 条标注集，不代表开放领域性能。

## 离线 Agent 验收

- 34 个单元/API/集成测试；
- V4：24 条固定路由回归；
- V5：12 条固定 Harness 案例，工具选择 12/12、任务完成 12/12、平均
  1.833 步；
- V5：4/4 故障注入请求从检查点恢复；
- GitHub Actions 在 Push/PR 自动运行上述离线门禁。

V5 指标使用 Fake Planner/Tool 的确定性回归集，适合发现代码回归，不是对真实
LLM 工具选择泛化能力的证明。本轮没有在当前临时 Python 环境重跑 GPU RAG 或
真实 DeepSeek 工具调用。

## 本地运行

推荐在 PyCharm 中新建 Python 3.10 虚拟环境。仓库旧 `.venv` 绑定的解释器
已失效，不要继续复用。

```powershell
py -3.10 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH="src"
```

复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`；默认模型为
`deepseek-chat`，可用 `DEEPSEEK_MODEL` 覆盖。API Key、数据、索引、模型和
运行日志均不提交 Git。

### 测试与评测

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe scripts\evaluate_agent_routes.py
& .\.venv\Scripts\python.exe scripts\evaluate_v5_harness.py
```

### V5 CLI

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli run `
  "Article 6.2 的要求是什么？请给本地证据"

# 相同 Request ID 可安全重试/恢复
& .\.venv\Scripts\python.exe -m carbon_agent.cli run `
  "查询 ACR102 的登记状态" --request-id demo-registry-001
```

### FastAPI

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli serve --port 8000
```

接口：`GET /health`、`POST /v1/agent/chat`、
`GET /v1/executions/{request_id}/events`；Swagger 位于
`http://127.0.0.1:8000/docs`。

```json
{
  "text": "查询 ACR102 的登记状态",
  "intent": "auto",
  "payload": {"project_id": "ACR102"},
  "actor_id": "demo-reviewer",
  "approval_granted": false,
  "request_id": "demo-registry-001"
}
```

### Streamlit

```powershell
& .\.venv\Scripts\python.exe -m streamlit run src\step_13_streamlit_app.py
```

界面会显示答案、来源、工具轨迹、运行元数据和可重放事件。

### MCP Server

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli mcp-server
```

stdio Server 支持 `initialize`、`tools/list`、`tools/call` 和 `ping`，仅暴露
`knowledge_search` 与 `registry_lookup`。风险审核工具不会通过 MCP 暴露。

## 数据与安全边界

- PDF、Excel、索引、模型、API Key、SQLite 和日志仅保存在本地；
- 登记记录来自 `v2026-02` 静态 Excel 快照，不代表登记机构实时状态；
- 风险模型验证数据有限，只能作为实验信号；
- 没有 SSO/RBAC、租户隔离、KMS、分布式队列、限流、容器编排、SLA、线上
  监控和真实流量压测；
- SQLite 检查点是单机恢复机制，不等于分布式 Lease、Outbox 或 Exactly-once；
- 系统不会自动输出企业绿洗、违法或合规结论。

## 项目结构

```text
src/carbon_agent/        # V1-V5 Agent、Harness、Tools、MCP、API/UI
src/step_01...23.py      # 原 RAG、登记表和风险模型链路
tests/                   # 34 个离线测试
data/eval/               # 检索、V4 路由、V5 Harness 回归集
scripts/                 # 可复现评测脚本
docs/releases/           # 每个大版本留档
docs/AGENT_PROJECT_REPORT.md
.github/workflows/       # 离线 CI 门禁
```
