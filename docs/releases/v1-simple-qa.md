# Agent V1：简单问答

## 版本目标

建立与原 RAG 解耦的最小 Agent 运行骨架：接收一个问题，通过模型网关返回结构化回答。本版本不使用记忆、知识库或业务工具。

## 本次交付

- `ChatGateway` 协议隔离模型供应商；
- `DeepSeekGateway` 从环境变量读取密钥与模型配置；
- `FakeGateway` 支持不联网、不消耗 Token 的确定性测试；
- `SimpleQAAgent` 实现输入校验、系统提示词和结构化 `AgentResponse`；
- CLI 入口支持在 PyCharm Terminal 中运行；
- 3 个离线单元测试覆盖正常回答、空问题和空模型响应。

## 运行与验收

```powershell
$env:PYTHONPATH="src"
python -m unittest tests.test_v1_simple_qa -v
python -m carbon_agent.cli ask "请解释碳信用与碳配额的区别"
```

第二条命令需要 `.env` 中存在有效的 `DEEPSEEK_API_KEY`。测试命令不需要 API。

## 当前边界

- 每次请求无状态；
- 不读取项目 PDF；
- 不调用登记表或风险模型；
- 不具备多 Agent 路由。

下一版本将加入持久化会话与多轮上下文窗口。
