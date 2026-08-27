# Agent V2：多轮持久化记忆

## 版本目标

让问答 Agent 能够在同一会话中理解前文，并在程序重启后继续读取历史，同时限制传入模型的上下文规模。

## 本次交付

- SQLite 会话库，持久化 `sessions` 与 `messages`；
- 用户消息与助手回答以一个事务写入，避免失败调用留下半截对话；
- 默认读取最近 12 条消息，防止上下文随会话无限增长；
- 每次返回 `session_id`、实际使用的历史条数和窗口上限；
- `chat` CLI 支持指定会话 ID 和数据库路径；
- 离线测试覆盖跨轮上下文、窗口裁剪和失败回滚。

## 运行与验收

```powershell
$env:PYTHONPATH="src"
python -m unittest tests.test_v1_simple_qa tests.test_v2_conversation -v

python -m carbon_agent.cli chat "记住我关注 CCER 项目登记" 
python -m carbon_agent.cli chat "我刚才关注什么？" --session-id 上一条返回的session_id
```

## 知识点

- 短期记忆不是把所有聊天记录无限塞进 Prompt，而是持久化存储加有限上下文窗口；
- 数据写入按完整 Turn 进行事务提交；
- `session_id` 将用户侧会话与 Agent 执行解耦；
- 模型网关继续保持可替换，记忆层不依赖具体大模型。

## 当前边界

本版本只有对话记忆，不会自动查询 PDF 知识库，也不会调用业务工具。下一版本接入现有混合检索与带页码证据回答。
