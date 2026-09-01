# Contributing

欢迎提交问题报告、文档修正和代码改进。

## 报告问题

Issue 请包含：

- 操作系统与 Python 版本；
- 使用的运行时：`langgraph` 或 `custom`；
- 可复现的命令和最小输入；
- 完整错误类型与必要日志，删除 API Key、用户内容和其他敏感信息；
- 预期行为与实际行为。

## 开发环境

```powershell
py -3.10 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

提交改动前运行：

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe scripts\evaluate_agent_routes.py
& .\.venv\Scripts\python.exe scripts\evaluate_v5_harness.py
& .\.venv\Scripts\python.exe scripts\evaluate_v6_runtime_comparison.py
```

新增工具必须提供参数 Schema、权限级别、错误策略和测试。涉及风险审核的工具必须
保留人工审批，不能将实验性模型输出改写为法律、合规或绿洗结论。

## Pull Request

Pull Request 应说明改动目的、验证命令和兼容性影响。不要提交 `.env`、API Key、
原始业务数据、模型权重、向量索引或本地运行数据库。
