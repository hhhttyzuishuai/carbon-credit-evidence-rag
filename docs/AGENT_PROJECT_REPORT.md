# 碳信用证据审核 Agent Harness 项目报告

## 1. 最终成果

原项目是一条完成标注评测的双语 RAG：处理 9 份 PDF，保留物理页码，组合
E5 Dense、BM25、RRF 和 Cross-Encoder，并让 DeepSeek 生成带引用回答。升级
没有推翻检索链，而是在外层建立可测试、可恢复、受权限约束的 Agent Harness。

V5 默认运行时会读取用户问题和当前观察，由模型决定调用 Knowledge、Registry、
Experimental Risk Review 中的一个工具，或直接结束回答。每次工具执行结果重新
进入上下文，形成最多 6 步的 `observe -> decide -> tool -> observe` 循环。

## 2. 版本留档

| 阶段 | 主要成果 | Commit | Tag |
|---|---|---|---|
| V1 | LLM Gateway、简单问答、Fake LLM 测试 | `22c1d1c` | `agent-v1.0.0` |
| V2 | SQLite 会话、原子 Turn、历史窗口 | `d772bf9` | `agent-v2.0.0` |
| V3 | RAG Adapter、知识 Agent、引用审计 | `c1df97f` | `agent-v3.0.0` |
| V4 | 确定性多 Agent、业务工具、授权、API | `d8f1e92` | `agent-v4.0.0` |
| V5 | Agent Loop、Tool Registry、恢复/重放、MCP | 本次发布 Commit | `agent-v5.0.0` |

V5 推送后可用 `git show agent-v5.0.0` 查看最终快照。各阶段设计保存在
`docs/releases/`，面试时可以真实展示从问答、记忆、RAG、业务工具到 Harness
可靠性的演进，而不是把最终代码一次性包装成“从零设计”。

## 3. 一次 V5 请求如何流转

1. API/CLI/UI 将文本、Session、Actor、Payload、审批状态和 Request ID 转为
   `AgentRequest`；
2. Execution Store 对规范化请求计算指纹：同 ID 同内容直接重放，同 ID 不同
   内容拒绝执行；
3. Harness 恢复已有检查点，或读取 SQLite 对话历史创建初始上下文；
4. 上下文超限时压缩旧消息，保留系统边界和最近 Turn；
5. Planner 看到统一工具 Schema，选择一个工具或最终回答；
6. Tool Registry 校验工具名、参数类型、必填字段、审批权限和重试预算；
7. 工具结果加入下一轮观察；超大结果保存为带 SHA-256 的 Artifact，只把预览
   和指针交给模型；
8. 每一步写入 SQLite Checkpoint 和 Event；进程中断后可用原 Request ID 继续；
9. 最终答案经过 Source ID 引用校验，再原子写入完整对话 Turn；
10. 返回 Answer、Sources、Tool Calls、恢复/压缩/引用元数据，并写脱敏审计。

系统不保存或展示隐藏思维链。事件只记录步骤、动作、工具名、状态和错误类型。

## 4. 关键知识点

### Agent Loop 不是关键词路由

V4 的 Router 能稳定处理四条固定路线，但执行路径在代码里预先决定。V5 把“下一
步做什么”交给模型：它可以依据工具观察修正参数、换工具或结束。工程层仍控制
最大步数、权限和输出验证，模型只拥有受约束的决策权。

### Tool Schema 与最小权限

工具不只是 Python 函数。`ToolSpec` 同时声明名称、用途、JSON Schema、审批要求
和重试次数。Risk Review 必须由调用方显式授权；MCP Server 只暴露只读 Knowledge
和 Registry，不会因为“接入协议”而扩大高风险权限。

### 幂等、检查点和重放

Request ID 对应请求指纹和最终响应。已完成请求重复提交不会再次调用模型/工具；
相同 ID 携带不同参数会冲突。工具步骤后保存消息、来源、工具轨迹和 Artifact，
失败请求能从最近检查点恢复。事件接口可还原执行过程。

这是单机 SQLite 的 At-least-once 风格原型，不宣称具备分布式 Exactly-once、
Lease 或事务 Outbox。

### 上下文治理

多轮记忆并不等于把所有历史无限塞入 Prompt。系统只把历史作为意图上下文，旧
消息超限后生成确定性摘要，最近消息保留；大工具输出存为内容寻址 Artifact，
避免单次观察占满上下文。历史回答不能冒充本轮业务证据。

### Grounding 与输出验证

Knowledge 返回 `[S编号]`，Registry 返回 `[T编号]`。最终回答使用不存在的编号，
或调用证据工具后完全没有有效引用，Harness 会拒绝把回答作为可靠结论输出。
物理页码、文件名、Workbook、Sheet 和 Excel 行号仍由底层链路保留。

### Human-in-the-loop

风险工具即使是只读，也可能被用户误解成正式结论，因此执行前要求显式审批。
它的输出始终带“实验性审核信号”边界，不能表述为企业绿洗、违法或合规结论。

### MCP

项目实现 stdio MCP 的初始化、工具发现、工具调用和 Ping，使外部 Agent Client
能复用本地知识与登记工具。实现覆盖当前演示所需的协议子集，不宣称覆盖所有
可选能力。

## 5. 验收证据

- 34 个离线测试通过；
- V4 的 24/24 固定路由案例继续通过；
- V5 的 12/12 固定案例工具选择正确、12/12 任务完成，平均 1.833 步；
- 4/4 故障注入请求在第二次提交时从检查点恢复；
- 测试覆盖幂等重放无二次 Planner 调用、ID 指纹冲突、工具瞬时失败重试、最大
  步数停止、引用校验、上下文压缩、Artifact Hash、MCP 只读边界和 API；
- 原 RAG 50 条人工标注问题中，Cross-Encoder Hit@1 0.780、Hit@3 0.980、
  MRR 0.863；
- 11,110 条本地登记记录支持 Project ID 精确查询及行级来源。

V5 回归使用确定性 Fake Planner/Tool，只用于防回归，不能证明真实模型面对任意
表达都能正确选工具。当前临时 Python 3.12 环境缺少 PyTorch，本次没有重跑 GPU
检索或真实 DeepSeek 工具调用；演示前需要在完整 Python/CUDA 环境补 live smoke。

## 6. 为什么只能称“伪企业级”

已具备的工程形态：契约化输入输出、受限 Agent Loop、统一 Tool Schema、最小
权限、持久化记忆、幂等、检查点、事件重放、上下文治理、来源验证、Human-in-the-
loop、脱敏审计、API/UI/MCP、自动测试、评测集、CI 和版本发布。

未具备的生产条件：企业 SSO/RBAC、租户隔离、Vault/KMS、PostgreSQL/Redis、
分布式任务、Lease/Outbox、限流熔断、容器编排、OpenTelemetry、SLA、告警、
真实流量压测、实时登记 API、大规模独立风险验证及法务/合规签核。

因此简历应使用“原型”“审核辅助”“实验性信号”，不要写“生产级企业系统”或
“自动识别绿洗”。

## 7. 简历项目说明

### 项目名称

碳信用证据审核 Agent Harness｜个人项目｜2026.08

### 技术栈

Python、FastAPI、SQLite、DeepSeek API、MCP、PyTorch、Sentence-Transformers、
Multilingual-E5、BM25、RRF、BGE Cross-Encoder、XGBoost、GitHub Actions

### 推荐三条描述

- 基于既有双语 RAG 设计受限 Agent Harness，实现模型驱动的
  `observe-decide-tool-observe` 循环和 Knowledge、Registry、Risk Review 统一
  Tool Registry，通过 JSON Schema、最大步数、重试预算和人工审批约束执行。
- 构建 Request ID 幂等、SQLite 检查点与事件重放机制，支持失败请求恢复；增加
  上下文压缩、SHA-256 大结果外置、Source ID 引用校验，并统一 CLI、FastAPI、
  Streamlit 与只读 MCP 工具服务。
- 复用 9 份中英文 PDF 的 E5+BM25+RRF+Cross-Encoder 检索链，在 50 条人工
  标注问题上取得 Hit@1 0.780、Hit@3 0.980、MRR 0.863；完成 34 项离线测试、
  24 条路由回归、12 条 Harness 回归及 4 次故障恢复验证。

### 一句话版本

设计并实现面向碳信用证据审核的可恢复 Agent Harness，将双语 RAG、持久化记忆
和业务工具统一到带幂等、检查点、MCP、引用验证与人工审批的 FastAPI 服务中。

## 8. 面试讲法

按“问题—演进—可靠性—验证—边界”讲：

1. 原 RAG 只解决证据检索，不能管理持续会话或自主选择业务工具；
2. V1–V4 先建立稳定契约、记忆、Grounding 和确定性多 Agent，再在 V5 引入
   模型驱动循环；
3. Agent 自主性由 Tool Schema、最大步数、审批、幂等、检查点和 Verifier 包围；
4. 展示 Git Tags、34 个测试、两组回归集、故障恢复事件和 RAG 标注指标；
5. 主动说明静态登记表、Fake Planner 回归、未重跑 GPU/live LLM 和未投产边界。

如果面试官问“为什么不用 LangGraph”，可以回答：本版用小型自定义 Harness
显式实现状态、循环、检查点、权限和事件，便于理解底层机制与单元测试；若进入
并行分支、人工中断长任务和分布式执行，再评估 LangGraph 或工作流引擎，而不是
用框架名代替系统设计。

## 9. 演示前检查

1. 在 PyCharm 重建 Python 3.10 `.venv`，按本机 CUDA 安装 PyTorch；
2. 安装依赖并配置 `.env`，录屏时不要展示密钥；
3. 运行 34 个测试、V4 路由回归和 V5 Harness 回归；
4. 重跑 50 条检索评测并执行真实 DeepSeek Tool Calling smoke test；
5. 演示知识检索、登记查询、风险未授权、相同 Request ID 重放和故障恢复；
6. 展示 API 事件和脱敏 Audit，避免提交包含真实输入的 Runtime 文件。
