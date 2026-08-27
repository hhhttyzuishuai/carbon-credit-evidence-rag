# Carbon Credit Evidence Review Multi-Agent

面向碳信用披露审核场景的可追溯多 Agent 原型。系统把通用问答、多轮记忆、PDF 知识库、登记记录查询和实验性风险审核拆成独立专家，由确定性 Router 编排，并通过引用校验、人工授权、Trace 和脱敏审计日志控制边界。

> 这是作品集级“伪企业级”工程原型，不是已经投产的企业系统，也不替代合规、法律、审计或绿洗判断。

## 四阶段版本

| 版本 | 能力 | Git 标签 |
|---|---|---|
| V1 | 无状态简单问答、可替换 LLM 网关 | `agent-v1.0.0` |
| V2 | SQLite 多轮记忆、原子 Turn、有限历史窗口 | `agent-v2.0.0` |
| V3 | Hybrid + Reranker 知识库、页码来源、引用审计 | `agent-v3.0.0` |
| V4 | 多 Agent 路由、登记/风险工具、授权、Trace、审计、FastAPI | `agent-v4.0.0` |

每个版本的目标、验收方法和边界保存在 [docs/releases](docs/releases)。完整复盘和简历材料见 [Agent 项目报告](docs/AGENT_PROJECT_REPORT.md)。

## 架构

```text
CLI / FastAPI
      |
      v
RouterAgent -------------------------------+
  |              |             |           |
  v              v             v           v
Conversation  Knowledge     Registry     RiskReview
Agent         Agent         Agent        Agent
  |              |             |           |
SQLite       Hybrid+CE      Excel       Evidence Gate
Memory       PDF RAG        Snapshot     + XGBoost
  |              |             |           |
  +--------------+-------------+-----------+
                         |
                         v
               OutputVerifierAgent
                         |
                 Response + Trace
                         |
                Redacted JSONL Audit
```

路由使用显式规则，便于审计和回归；它不是用 LLM 猜测后直接执行高风险工具。API 调用方也可以显式传入 `intent`，业务系统不必依赖自然语言路由。

## 核心能力

- `ChatGateway` 隔离模型供应商，DeepSeek 与 Fake LLM 可替换；
- SQLite 跨进程会话记忆，完整用户/助手 Turn 在一个事务中提交；
- 复用原有 E5 Dense、BM25、RRF 和 BGE Cross-Encoder 检索链路；
- 知识回答只允许引用本轮 `[S编号]`，无证据、无引用或越界引用会降级；
- `RegistryAgent` 按 Project ID 精确查询 11,110 条本地登记记录快照；
- `RiskReviewAgent` 仅在显式授权后调用实验模型，最终仍要求人工复核；
- 每次编排返回 `request_id`、`trace_id`、route、latency、tool calls 和 sources；
- JSONL 审计日志递归脱敏 Key、Token、Secret、Password；
- FastAPI 提供健康检查和统一 Agent 接口；
- 20 个离线测试与 24 条固定路由回归案例。

## 原 RAG 评测

当前语料为 9 份静态中英文 PDF，共 797 页、2,572 个 Chunks。50 条人工标注问题以来源文件和物理页码为相关性标准。

| 方法 | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Dense Retrieval | 0.540 | 0.720 | 0.656 |
| BM25 | 0.680 | 0.880 | 0.785 |
| RRF Hybrid Retrieval | 0.580 | 0.820 | 0.722 |
| Cross-Encoder Reranker | **0.780** | **0.980** | **0.863** |

这些结果只适用于当前静态语料和 50 条标注集，不代表开放领域性能。

## 本地运行

推荐在 PyCharm 中选择 Python 3.10，并重新创建虚拟环境。当前仓库原 `.venv` 绑定的解释器路径已失效，不应继续复用。

```powershell
py -3.10 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH="src"
```

复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`。本地数据、索引、模型、API Key 和运行日志均不提交 Git。

### 跑测试和路由评测

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe scripts\evaluate_agent_routes.py
```

### 使用多 Agent CLI

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli run "查询 ACR102 的登记状态"
& .\.venv\Scripts\python.exe -m carbon_agent.cli run "管理办法对项目登记有何规定？"
```

### 启动 API

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli serve --host 127.0.0.1 --port 8000
```

接口：`GET /health`、`POST /v1/agent/chat`，Swagger UI 位于 `http://127.0.0.1:8000/docs`。

```json
{
  "text": "查询 ACR102 的登记状态",
  "intent": "registry",
  "payload": {"project_id": "ACR102"},
  "actor_id": "demo-reviewer",
  "approval_granted": false
}
```

## 数据与安全边界

- PDF、Excel、索引、模型、API Key 和运行日志仅保存在本地；
- 登记记录来自 `v2026-02` 静态 Excel 快照，不代表实时状态；
- 风险模型的真实严格验证集很小，模型分数只作为实验信号；
- 系统不自动输出企业绿洗、违法或合规结论；
- 未接企业 SSO、密钥管理、分布式任务、容器编排、线上监控或真实流量压测；
- 路由评测是固定意图回归集，不是开放域泛化证明。

## 项目结构

```text
src/carbon_agent/        # V1-V4 Agent 核心
src/step_01...23.py      # 原 RAG、登记表和风险模型链路
tests/                   # 离线单元与集成测试
data/eval/               # 检索与 Agent 路由评测集
scripts/                 # 可复现评测脚本
docs/releases/           # 每个大版本留档
docs/AGENT_PROJECT_REPORT.md
.github/workflows/       # 离线 CI 门禁
```
