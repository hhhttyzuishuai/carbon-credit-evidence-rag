# Runtime comparison

本项目保留 Custom Harness 和 LangGraph Runtime。两者使用同一组模型消息、工具
Schema、业务处理函数、审批策略和验证逻辑，因此可以单独比较编排层。

## 结构

| 对比项 | Custom Harness | LangGraph Runtime |
|---|---|---|
| 入口 | `AgentHarness.handle()` | `LangGraphAgentRuntime.handle()` |
| 模型适配 | `DeepSeekToolPlanner` | `LangChainDeepSeekPlanner` |
| 工具描述 | 自定义 JSON Schema `ToolSpec` | LangChain `StructuredTool` |
| 循环 | Python `while` 有界循环 | `StateGraph` 条件边 |
| 状态持久化 | `SQLiteExecutionStore` | `SqliteSaver` + Execution Store |
| 输出验证 | 共用 `verify_grounded_answer()` | 共用 `verify_grounded_answer()` |
| 最大步数 | 6 | 6 |
| 运行时选择 | `--runtime custom` | `--runtime langgraph` |

## 共用组件

两套运行时不会各自实现一套业务逻辑。以下组件保持一致：

- `knowledge_search`：Hybrid Retrieval 和 Cross-Encoder Reranker；
- `registry_lookup`：Project ID 精确查询与行级来源；
- `experimental_risk_review`：显式审批后才能执行；
- Tool Registry：参数 Schema、重试次数、权限和错误类型；
- Conversation Store：SQLite 多轮历史；
- Artifact Store：大工具结果外置并记录 SHA-256；
- Output Verifier：检查 Source ID 和风险输出边界；
- Audit Log：结构化事件和递归脱敏。

## 执行流程

Custom Harness 在 Python 循环中依次执行 Planner、工具和 Verifier。每次状态变化
都写入 Execution Store，进程异常后根据最近检查点恢复。

LangGraph Runtime 将相同步骤拆成三个节点：

```text
START -> planner -> tool_executor -> planner
                  \-> output_verifier -> END
```

LangGraph Checkpointer 保存节点状态；Execution Store 继续负责请求指纹、幂等结果
和对外事件记录。两层存储职责不同，避免把框架检查点直接当作业务幂等接口。

## 固定回归结果

`data/eval/v5_tool_cases.jsonl` 包含 12 条确定性任务。Fake Planner 与 Fake Tool
用于隔离网络和模型波动，只测试工具选择、循环结束、检查点和错误恢复。

| 指标 | Custom Harness | LangGraph Runtime |
|---|---:|---:|
| 工具选择 | 12/12 | 12/12 |
| 任务完成 | 12/12 | 12/12 |
| 平均步骤 | 1.833 | 1.833 |
| 故障恢复 | 4/4 | 4/4 |
| 本地中位编排耗时 | 71.45 ms | 104.40 ms |

延迟数据来自一次本地确定性运行，只包含 Python、SQLite 和框架编排，不包含 LLM、
网络或 GPU 检索。它不能用于判断真实服务吞吐量，也不能说明某个运行时在业务质量
上更好。

## 选择建议

Custom Harness 的依赖较少，状态转移都在项目代码中，适合需要完全控制执行细节的
场景。LangGraph Runtime 提供标准状态图、节点检查点和图结构读取，更适合继续增加
节点、子图或外部观测能力。

默认运行时是 LangGraph。可以通过 CLI 参数或环境变量切换：

```powershell
& .\.venv\Scripts\python.exe -m carbon_agent.cli run "question" --runtime custom
$env:AGENT_RUNTIME="custom"
```

固定回归集不是开放域 Agent 基准。接入新的模型、工具或审批流程后，应扩充用例并
重新运行两个运行时，检查行为是否仍然一致。
