# 碳信用披露审核 Agent 系统项目报告

## 项目概述

系统面向碳信用披露审核，接收自然语言问题后选择知识检索、登记查询或实验性风险
审核工具，并返回可定位到文件、物理页码、工作表和数据行的结果。模型负责选择
下一步行动，工程层负责参数校验、最大步数、审批、幂等、检查点和引用验证。

当前同时保留两套运行时：V5 是自研 Agent Harness，V6 使用 LangGraph 和
LangChain 重构编排层。两版共用数据、工具和回归集，因此可以直接观察框架化前后
的代码结构、状态管理和执行开销。

## 版本记录

| 版本 | 内容 | Tag |
|---|---|---|
| V1 | 简单问答与 LLM Gateway | `agent-v1.0.0` |
| V2 | SQLite 多轮记忆 | `agent-v2.0.0` |
| V3 | 知识检索、页码来源和引用审计 | `agent-v3.0.0` |
| V4 | 确定性多 Agent 路由和业务工具 | `agent-v4.0.0` |
| V5 | 自研工具循环、幂等、检查点、MCP | `agent-v5.0.0` |
| V6 | LangGraph、LangChain、双运行时和可视化 | `agent-v6.0.0` |

详细发布说明位于 `docs/releases/`。

## V6 执行链路

1. API、CLI 或 Streamlit 将问题、Session、Actor、审批状态和 Request ID 组成
   `AgentRequest`；
2. Execution Store 计算请求指纹，拦截同 ID 不同内容的请求，已完成请求直接
   返回原结果；
3. LangGraph Checkpointer 创建或恢复对应 `thread_id` 的节点状态；
4. Planner 节点通过 `ChatDeepSeek` 读取消息和 LangChain Tool Schema，选择工具
   或结束；
5. Tool Executor 使用 `StructuredTool` 执行参数验证、审批和重试，再把结果写回
   Graph State；
6. 条件边把工具观察重新送回 Planner，最多循环6步；
7. Output Verifier 检查本轮 Source ID 和业务边界；
8. 完整 Turn、最终响应和执行事件分别写入 SQLite 与脱敏 Audit Log。

知识检索和登记查询成功后，回答必须引用本轮生成的 `[S编号]` 或 `[T编号]`。
历史对话只用于理解问题，不能作为事实来源。

## 两套运行时

### V5 Custom Harness

V5 直接用 Python 实现工具循环。`AgentHarness` 控制状态、重试和停止条件，
`ToolRegistry` 管理 JSON Schema 与审批策略，`SQLiteExecutionStore` 保存检查点
和幂等响应。优点是机制直观、依赖较少，也便于解释每一步为什么存在。

### V6 LangGraph

V6 把 Planner、Tool Executor 和 Output Verifier 变成 StateGraph 节点，并用
条件边表达工具循环。模型由 `langchain-deepseek` 接入，工具转换为 LangChain
`StructuredTool`，节点状态由 LangGraph SQLite Checkpointer 保存。Graph 可以
被程序读取并展示在 API 和 Streamlit 页面中。

V6 没有删除 V5，也没有重新实现底层知识库。框架层发生变化，业务工具和安全规则
保持一致，这让对比更接近真实的软件迁移。

## 数据和工具

### 知识检索

- 9份中英文 PDF、797页、2,572个文本块；
- Multilingual-E5 Dense Retrieval；
- 中文分词 BM25；
- RRF 排名融合；
- BGE Cross-Encoder 重排序；
- 文件名、语言、文档类型和物理页码来源。

50条人工标注问题上的结果：

| 方法 | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Dense | 0.540 | 0.720 | 0.656 |
| BM25 | 0.680 | 0.880 | 0.785 |
| RRF Hybrid | 0.580 | 0.820 | 0.722 |
| Cross-Encoder | 0.780 | 0.980 | 0.863 |

### 登记查询

本地静态快照包含11,110条记录。工具按 Project ID 精确查询，并返回工作簿、Sheet
和 Excel 行号。静态快照不能代表登记机构的实时状态。

### 实验性风险审核

风险工具要求 `approval_granted=true`，否则在执行前停止。结果只用于辅助人工核查，
不会输出企业绿洗、违法或合规结论。

## 验收结果

- 42个离线测试通过；
- V4路由回归24/24；
- V5和V6在同一12条任务上均为工具选择12/12、任务完成12/12；
- 两版平均执行步数均为1.833；
- 两版故障注入恢复均为4/4；
- V6测试覆盖 Graph节点、条件边、StructuredTool、审批、幂等、引用校验和失败
  节点恢复；
- Streamlit首页、状态图和双运行时对比页已完成本地浏览器视觉检查。

一次本地确定性回归中，V5中位编排耗时为88.37 ms，V6为123.68 ms。该测试不含
LLM、网络和 GPU 检索，只能说明当前 Fixture 下 LangGraph 增加了一定框架开销，
不能作为线上性能结论。

## 可视化

Streamlit 控制台提供四个页面：

1. Agent 控制台：切换 V5/V6，查看回答、来源、工具调用和事件；
2. 执行图：显示 Planner、Tool Executor、Verifier 及条件边；
3. V5/V6 对比：展示同一回归集的完成率、恢复率、步骤和本地开销；
4. 评测与证据：展示 Dense、BM25、RRF 和 Cross-Encoder 指标。

GitHub README 同时嵌入 SVG 架构图，即使不运行 Python 也能了解系统结构。

## 简历材料

推荐标题：**碳信用披露审核 Agent 系统**

可直接使用的完整版和精简版位于
[`V5_V6_RESUME_COMPARISON.md`](V5_V6_RESUME_COMPARISON.md)。

项目地址：<https://github.com/hhhttyzuishuai/carbon-credit-evidence-rag>

## 面试重点

### 为什么保留两个运行时

V5用来说明对Agent循环、状态和恢复机制的理解，V6用来说明如何把自研实现迁移到
主流框架。两版共用回归集，避免只展示框架代码而无法判断行为是否一致。

### 为什么不是多 Agent 互相讨论

当前任务主要是工具选择和受控执行，单个 Planner 加窄权限工具更容易测试和审计。
V4保留了职责拆分的多 Agent 实现，但V6没有为了简历关键词增加无必要的对话成本。
如果出现需要独立上下文、不同权限或并行处理的任务，再把专业节点拆为子图更合理。

### 为什么不能称为生产级

项目没有企业 SSO/RBAC、租户隔离、KMS、分布式队列、PostgreSQL Checkpointer、
OpenTelemetry、SLA、线上告警和真实流量压测。SQLite适合本地作品集和小型演示，
不是生产部署证明。

## 演示前检查

1. 在 PyCharm 创建 Python3.10虚拟环境并安装依赖；
2. 按本机 CUDA 安装 PyTorch，重跑50条检索评测；
3. 配置 DeepSeek Key，分别执行 V5和V6真实 Tool Calling；
4. 运行42个测试和全部三组 Agent 回归脚本；
5. 启动 Streamlit，演示运行时切换、执行图、事件和引用来源；
6. 不展示或提交 API Key、真实用户输入和 Runtime 数据库。
