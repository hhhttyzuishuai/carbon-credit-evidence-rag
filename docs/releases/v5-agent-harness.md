# V5 — 可恢复 Agent Harness

## 目标

把 V4 的确定性路由升级为真正的 `observe -> decide -> tool -> observe -> final`
循环，同时补齐作品集项目最能体现工程能力的可靠性机制。V1–V4 源码与 Git
标签继续保留，便于比较演进过程。

## 本版新增

- `DeepSeekToolPlanner`：模型每一步选择一个工具或结束回答；
- `ToolRegistry`：统一 JSON Schema、参数校验、审批要求和重试次数；
- `AgentHarness`：最多 6 步的受限循环、引用校验和安全停止；
- `SQLiteExecutionStore`：Request ID 幂等、指纹冲突检测、检查点和事件流；
- 失败恢复：失败请求用相同 Request ID 重试时从最近检查点继续；
- `ContextWindowManager`：保留最近消息，确定性压缩较早上下文；
- `ArtifactStore`：大工具输出按 SHA-256 外置，模型只接收预览和文件指针；
- MCP stdio Server：只暴露知识检索和登记查询，不暴露风险审核；
- CLI、FastAPI、Streamlit 统一使用同一个 V5 Runtime；
- `GET /v1/executions/{request_id}/events` 查询可重放执行事件。

## 验收

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
python scripts/evaluate_v5_harness.py
```

当前离线结果：34 个测试通过；12/12 固定案例工具选择正确，12/12 完成，
平均 1.833 步；4/4 故障注入请求从检查点恢复。延迟只是在本机执行 Fake
Tool 的 SQLite 回归耗时，不能代表真实 LLM 或 GPU RAG 延迟。

## 安全与权限

- 风险审核工具继续要求 `approval_granted=true`；
- MCP 只暴露只读知识和登记工具；
- 知识/登记工具执行后，最终回答必须引用本轮有效 Source ID；
- 最大步数防止无界循环；
- 审计事件不记录隐藏思维链，也不保存 API Key；
- 登记数据仍是静态快照，风险输出仍不是法律、合规或绿洗结论。

## 已知边界

- SQLite 适合单机原型，不等于分布式队列、Lease 或 Outbox；
- 没有企业 SSO/RBAC、租户隔离、限流、KMS 和线上监控；
- 12 条回归案例由固定规则与 Fixture 构造，只证明代码没有回归；
- 本次环境未重跑 GPU 检索和真实 DeepSeek 工具调用，演示前需在完整
  Python/CUDA 环境执行 live smoke test；
- MCP 实现覆盖本项目使用的 initialize、tools/list、tools/call 和 ping，不宣称
  已覆盖协议的全部可选能力。
