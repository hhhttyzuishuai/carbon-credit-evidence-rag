# V6 — LangGraph 双运行时与可视化

## 目标

保留 V5 自研 Harness 作为可解释的底层实现，同时新增一套真正使用 LangGraph、
LangChain 和 DeepSeek 官方集成的运行时。两版复用同一组业务工具、证据校验、
审批规则和回归数据，避免通过更换任务制造对比结果。

## 实现

- `LangGraphAgentRuntime` 使用 `StateGraph` 定义 Planner、Tool Executor 和
  Output Verifier 三个节点；
- Planner 与 Tool Executor 之间通过条件边形成受限反馈循环；
- `LangChainDeepSeekPlanner` 使用官方 `ChatDeepSeek` 和标准 Tool Call；
- 原 `ToolSpec` 动态转换为 Pydantic Schema 和 LangChain `StructuredTool`；
- SQLite `SqliteSaver` 保存 LangGraph 节点状态，原 Execution Store 继续负责
  Request ID 幂等、事件查询和最终响应缓存；
- CLI 支持 `--runtime langgraph|custom`，默认使用 LangGraph；
- API 新增 `/v1/architecture`，健康检查版本更新为6.0.0；
- Streamlit 增加运行时切换、状态图、双运行时对比和检索评测图；
- README 嵌入 V6 SVG 架构图，GitHub 打开仓库即可看到系统结构。

## 依赖版本

- LangChain 1.3.18
- LangGraph 1.2.11
- langchain-deepseek 1.1.0
- langgraph-checkpoint-sqlite 3.1.1

这些版本在2026-08-29通过 PyPI 查询并在隔离 Python 3.12 环境完成导入和测试；
项目声明的最低 Python 版本仍为3.10。

## 离线验收

- 42个离线测试；
- V6测试覆盖 StateGraph 节点执行、条件路由、StructuredTool Schema、引用校验、
  审批、幂等和失败节点恢复；
- V5与V6共同运行12条固定任务，两版工具选择、任务完成和恢复结果一致；
- Streamlit 的控制台、执行图和对比页已在本地浏览器完成视觉检查。

## 对比结果

| 指标 | V5 Custom | V6 LangGraph |
|---|---:|---:|
| 工具选择 | 12/12 | 12/12 |
| 任务完成 | 12/12 | 12/12 |
| 平均步骤 | 1.833 | 1.833 |
| 故障恢复 | 4/4 | 4/4 |
| 本地中位编排耗时 | 88.37 ms | 123.68 ms |

延迟只反映本次 Fake Planner、Fake Tool 和 SQLite 的本机编排开销，不包含真实
DeepSeek、网络或 GPU RAG。该数字只能用于观察框架开销，不能用于宣称生产性能。

## 当前边界

- V6 使用 SQLite Checkpointer，适合本地和小型演示，不是分布式生产存储；
- 审批仍由请求字段控制，没有实现跨系统审批队列和 LangGraph动态 Interrupt；
- 本次环境没有 PyTorch，因此未重跑 GPU 检索；
- 真实 DeepSeek Tool Calling 需要用户本地 API Key，本次离线测试使用 Fake Planner；
- 可视化是本地 Streamlit 应用，GitHub 地址提供源码和架构图，不等同于公网服务。
