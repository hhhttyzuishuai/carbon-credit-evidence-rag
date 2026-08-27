# Agent V4：多 Agent 业务工具闭环

## 版本目标

形成一个可演示、可审计、可评测的“伪企业级”碳信用审核辅助 Agent。这里的“企业级”指工程结构与安全边界接近真实系统，而不是宣称已经通过生产流量、合规审计或大规模数据验证。

## 多 Agent 职责

```text
用户/API
  -> RouterAgent（确定性意图路由）
      -> ConversationAgent（通用多轮问答）
      -> KnowledgeAgent（PDF 证据检索与引用回答）
      -> RegistryAgent（Project ID 精确查询）
      -> RiskReviewAgent（证据门控后的实验性评分）
  -> OutputVerifierAgent（来源与输出契约校验）
  -> 脱敏 JSONL 审计日志
```

## 本次交付

- 自动路由与显式 `intent` 双模式；
- 专家 Agent 的职责、输入和输出边界分离；
- 登记表工具执行精确查询，返回工作簿、Sheet 和 Excel 行号；
- 实验性风险工具默认要求 `approval_granted=true`；
- Specialist 异常由 Orchestrator 隔离，外部只收到安全错误，审计记录错误类型；
- 每次响应包含 `request_id`、`trace_id`、路由、耗时、工具调用和来源；
- 审计日志递归脱敏 API Key、Token、Secret 和 Password；
- FastAPI 提供 `/health` 与 `/v1/agent/chat`；
- 离线回归测试覆盖四类路由、工具授权、来源溯源、脱敏和故障隔离。

## 运行

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v

python -m carbon_agent.cli run "查询 ACR102 的登记状态"
python -m carbon_agent.cli serve --host 127.0.0.1 --port 8000
```

测试环境额外安装 `requirements-dev.txt`；当前 Starlette 测试客户端使用 `httpx2`。

API 示例：

```json
{
  "text": "查询 ACR102 的登记状态",
  "intent": "registry",
  "payload": {"project_id": "ACR102"},
  "actor_id": "demo-reviewer"
}
```

## 安全与真实性边界

- 登记表是本地静态快照，不代表实时状态；
- 风险模型只提供实验性信号，所有决策仍是 `review_required`；
- 风险审核不等于绿洗、违法或合规认定；
- 当前不是生产系统：尚未接入企业 SSO、外部密钥管理、分布式队列、容器编排、线上告警或真实用户压测；
- “多 Agent”是职责分工与可独立测试的 Orchestration，不宣称模型具有自主决策权。
