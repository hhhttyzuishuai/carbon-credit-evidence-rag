# 碳信用证据审核多 Agent 项目报告

## 1. 最终做成了什么

原项目是一条已经完成评测的双语 RAG：处理 9 份 PDF，保留物理页码与来源元数据，组合 E5 Dense、BM25、RRF 和 Cross-Encoder，并通过 DeepSeek 生成带引用的回答。本次升级没有推翻这条链路，而是在它外面建立一个可独立测试的 Agent 系统。

最终系统包含 6 类职责：

1. `RouterAgent`：根据显式意图、结构化 Payload 和可审计关键词选择路线；
2. `ConversationAgent`：通用问答和 SQLite 多轮记忆；
3. `KnowledgeAgent`：调用原 RAG，生成本轮证据约束回答；
4. `RegistryAgent`：按 Project ID 精确查询本地登记表；
5. `RiskReviewAgent`：显式授权后执行证据门控与实验性风险评分；
6. `OutputVerifierAgent`：检查输出代理身份、答案非空和业务来源契约。

`MultiAgentOrchestrator` 负责分流、异常隔离、耗时统计和审计记录。对外提供 CLI 和 FastAPI 两种入口。

## 2. 版本与留档

| 阶段 | 主要成果 | Commit | Tag |
|---|---|---|---|
| V1 | LLM Gateway、简单问答、Fake LLM 测试 | `22c1d1c` | `agent-v1.0.0` |
| V2 | SQLite 会话、原子 Turn、历史窗口 | `d772bf9` | `agent-v2.0.0` |
| V3 | RAG Adapter、知识 Agent、引用审计 | `c1df97f` | `agent-v3.0.0` |
| V4 | 多 Agent、业务工具、授权、Trace、API | `d8f1e92` | `agent-v4.0.0` |

各阶段的目标、验收和当时边界均位于 `docs/releases/`。这比只保留最终代码更适合面试时解释“系统如何逐步演进”。

## 3. 一次请求如何流转

以“查询 ACR102 的登记状态”为例：

1. API 将文本、`actor_id`、`session_id`、意图和 Payload 转为 `AgentRequest`；
2. Router 将请求分到 `registry`；
3. Registry Agent 提取并标准化 `ACR102`；
4. Tool 对本地 11,110 条项目索引进行精确查询，不让 LLM 猜数字；
5. Agent 返回项目状态、签发/注销/剩余数量以及工作簿、Sheet、Excel 行号；
6. Verifier 要求成功的 Registry 回答必须带来源；
7. Orchestrator 写入 route、trace、耗时、工具状态和来源数量，敏感字段被脱敏；
8. API 返回统一 `AgentResponse`。

知识问答路线类似，但 Tool 换为 `Hybrid top-20 -> Cross-Encoder top-k`，Verifier 前还有 `[S编号]` 引用审计。风险路线则先检查 `approval_granted`，再进入证据门槛；即使模型被执行，也只返回 `review_required` 和实验信号。

## 4. 关键知识点

### Agent 与 RAG 的区别

RAG 解决“从哪里找证据并基于证据回答”；Agent 还需要判断任务类型、管理状态、选择工具、执行策略、处理失败并记录过程。本项目的 Agent 价值主要在 Orchestration 和业务边界，而不是多写了几个 Prompt。

### 多 Agent 不是多个模型互相聊天

这里按职责拆分 Agent，是为了让每个模块拥有窄输入、窄权限和独立测试。Router 没有登记表写权限，Knowledge Agent 不能调用风险模型，Registry Agent 不让 LLM 计算项目数字。这样比“所有 Agent 都能调用所有工具”更接近真实业务系统。

### 多轮记忆

对话历史保存在 SQLite，而不是存在 Python 全局变量中，因此进程重启后仍可恢复。系统默认只取最近窗口，防止 Token 无限增长。用户和助手两条消息在一个事务中提交；模型失败不会写入半个 Turn。

### Grounding 与引用审计

知识回答中的 `[S1]` 只对应本轮检索结果。历史对话能帮助理解指代，但不能成为事实来源。无证据、无引用和越界引用都会进入显式降级。

### Tool Use 与 Human-in-the-loop

登记查询是确定性只读工具。风险评分虽然也是只读，但业务含义敏感，因此要求调用方显式授权，并保留输入证据与工具状态。系统不把模型概率直接映射为企业风险结论。

### 可观测性与故障隔离

每次请求都有 `request_id` 和 `trace_id`，响应包含 route、latency、tool calls、sources。专家异常由 Orchestrator 捕获，用户看不到内部错误文本，审计日志只记录错误类型。敏感键递归脱敏。

### 评测分层

- 原 RAG：50 条人工标注双语问题，以来源文件和物理页码评估 Hit@K/MRR；
- Agent 核心：20 个离线单元/集成/API 测试；
- Router：24 条固定回归案例；
- CI：每次 Push/PR 执行离线测试和路由评测。

路由回归集由当前规则共同设计，适合防止代码改坏，但不能说明面对任意用户表达都能 100% 正确路由。

## 5. 当前验收证据

- 20 个离线测试通过；
- 24/24 固定路由案例通过；
- FastAPI `/health` 返回 HTTP 200；
- API 对空文本返回 HTTP 422；
- 真实本地 `ACR102` 完成精确查询，来源定位到 `PROJECTS` Sheet 第 5 行；
- V1、V2、V3、V4 均已提交、打 Tag 并推送 GitHub；
- 原 RAG 的 50 条评测中，Cross-Encoder：Hit@1 0.780、Hit@3 0.980、MRR 0.863。

GPU 知识检索本轮未重新执行：工作区旧 `.venv` 绑定的 Python 3.10 已从机器移除，而当前可用的临时 Python 3.12 环境没有 PyTorch。原有索引和既往评测产物仍在本地，但面试或演示前应按 README 重建 Python 3.10 环境并再次跑检索评测。

## 6. 为什么称为“伪企业级”

已经具备的企业工程形态：契约化请求/响应、专家职责和工具权限隔离、持久化会话、来源追踪与安全降级、Human-in-the-loop 授权、Trace/耗时/脱敏审计、HTTP 服务、离线测试、固定评测、CI 门禁和多版本发布记录。

仍未具备的生产条件：企业账号体系、RBAC/SSO、租户隔离、Vault/KMS、PostgreSQL/Redis、队列、限流、熔断、容器编排、SLA、线上监控告警、真实压测、实时登记机构 API、大规模独立真实风险验证及法务/合规签核。

因此简历中应使用“原型”“审核辅助”“实验性信号”，不要写“企业级生产系统”或“自动识别绿洗”。

## 7. 简历项目说明

### 项目名称

碳信用证据审核多 Agent 系统｜个人项目｜2026.08

### 技术栈

Python、FastAPI、SQLite、DeepSeek API、PyTorch、Sentence-Transformers、Multilingual-E5、BM25、RRF、BGE Cross-Encoder、XGBoost、TreeSHAP、GitHub Actions

### 三条简历描述

- 基于既有双语 RAG 升级碳信用披露审核多 Agent 原型，拆分 Router、Conversation、Knowledge、Registry、Risk Review 与 Verifier 职责，实现通用问答、多轮记忆、知识检索和结构化业务工具的统一编排。
- 构建 9 份中英文 PDF 的页码级溯源链路，组合 Multilingual-E5、BM25、RRF 与 BGE Cross-Encoder；在 50 条人工标注问题上取得 Hit@1 0.780、Hit@3 0.980、MRR 0.863，并实现本轮引用校验与证据不足安全降级。
- 使用 SQLite 实现原子化会话记忆，接入 11,110 条登记记录的 Project ID 精确查询与实验性风险审核；增加显式授权、Trace、脱敏 JSONL 审计、FastAPI、20 项离线测试和 24 条路由回归案例。

### 一句话版本

设计并实现面向碳信用披露审核的可追溯多 Agent 原型，将多轮记忆、双语 RAG、登记表精确查询和实验性风险工具统一到带引用校验、人工授权、Trace 与审计日志的 FastAPI 服务中。

## 8. 面试讲法

可以按“问题—设计—验证—边界”讲：

1. 问题：原 RAG 只能回答 PDF 问题，不能处理通用对话、持续会话或登记表/风险模型工具；
2. 设计：保留已评测 RAG，用 Adapter 接入 Knowledge Agent，再用 Router 和窄权限专家组织任务；
3. 验证：展示四个 Git Tag、20 个测试、24 条路由集、RAG 50 条评测，以及 ACR102 的行级来源；
4. 边界：说明登记表非实时、路由集非泛化证明、风险模型不做自动结论、项目尚未投产。

若面试官问“为什么不用 LangGraph”，可以回答：第一版先用自定义的确定性编排把状态、路由、工具权限和审计机制做清楚，降低框架黑盒；如果后续需要并行节点、检查点恢复和复杂状态图，再评估 LangGraph，而不是先用框架名替代系统设计。

## 9. 演示前检查

1. 在 PyCharm 新建 Python 3.10 `.venv`；
2. 安装 `requirements-dev.txt`，确认 CUDA/PyTorch 与本机匹配；
3. 配置 `.env`，不要录屏展示密钥；
4. 运行 20 个测试和 24 条路由评测；
5. 重跑 `step_11_evaluate_retrieval.py`，核对 50 条检索指标；
6. 演示通用多轮、法规证据问答、ACR102 精确查询、未授权风险请求四条路径；
7. 展示 `runtime/audit.jsonl` 中的 trace，但不要提交包含真实输入的运行日志。
