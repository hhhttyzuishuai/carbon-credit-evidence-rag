# V5 / V6 对比与简历写法

## 推荐项目标题

**碳信用披露审核 Agent 系统**

标题不写“RAG 升级”“框架迁移项目”或“伪企业级”。知识检索是 Agent 使用的
一项能力，不是项目主线。

## 可直接写入简历

**2025.03–2026.08　　碳信用披露审核 Agent 系统　　独立完成**

面向碳信用披露审核场景，设计能够根据问题自主选择知识检索、项目登记查询和
实验性风险审核工具的 Agent 系统，覆盖政策问答、项目核验和声明风险初筛。

在 V5 中独立实现 Agent 执行引擎，完成模型决策、工具注册、参数校验、最大步数、
请求幂等、SQLite 检查点和异常恢复；V6 使用 LangGraph StateGraph 重构编排层，
通过 LangChain StructuredTool 统一工具接口，并保留相同的证据与审批规则。

构建 9 份中英文 PDF、797 页、2,572 个文本块的证据库，组合 Multilingual-E5、
BM25、RRF 与 BGE Cross-Encoder；在 50 条人工标注问题上取得 Hit@1 0.780、
Hit@3 0.980、MRR 0.863，并接入 11,110 条登记记录实现 Project ID 精确查询和
行级来源追踪。

使用同一12条任务对两套运行时进行回归，V5和V6均完成12/12工具选择、12/12任务
执行及4/4故障恢复；提供 FastAPI、MCP 和 Streamlit 可视化控制台，可查看状态图、
工具轨迹、证据来源及双运行时指标。

**技术栈：** Python、LangGraph、LangChain、DeepSeek API、FastAPI、SQLite、
MCP、Streamlit、Multilingual-E5、BM25、RRF、BGE Cross-Encoder、GitHub Actions

**项目地址：** <https://github.com/hhhttyzuishuai/carbon-credit-evidence-rag>

## 一页简历的精简版

**2025.03–2026.08　　碳信用披露审核 Agent 系统　　独立完成**

面向碳信用披露审核场景，设计可自主选择知识检索、登记查询和实验性风险审核工具
的 Agent 系统；在 V5 中实现工具循环、幂等、检查点及异常恢复，在 V6 中使用
LangGraph StateGraph 和 LangChain StructuredTool 重构编排层，并通过 Streamlit
展示执行图、工具轨迹与来源。

处理9份中英文 PDF、797页和2,572个文本块，组合 E5、BM25、RRF 与
Cross-Encoder，在50条人工标注问题上取得 Hit@1 0.780、Hit@3 0.980、MRR
0.863；接入11,110条项目登记记录，并完成42项离线测试及V5/V6同集对比。

**技术栈：** Python、LangGraph、LangChain、DeepSeek API、FastAPI、SQLite、
MCP、Streamlit、Multilingual-E5、BM25、RRF、BGE Cross-Encoder

**项目地址：** <https://github.com/hhhttyzuishuai/carbon-credit-evidence-rag>

## 面试时如何解释两版

可以用下面这段，不需要贬低任何一版：

> V5 是我自己实现的受限 Agent Harness，目的是把模型决策、工具调用、幂等和
> 检查点机制写清楚。V6 保留相同工具和评测集，使用 LangGraph 重构编排层，
> 让我可以直接比较自研循环与框架化状态图。两版在固定回归集上的完成结果一致，
> LangGraph 版的优势主要是状态图标准化、节点可视化和后续扩展，而不是当前小型
> 回归集上的速度。

## 不能写进简历的说法

- “生产级企业 Agent”：没有真实流量、企业鉴权和线上 SLA；
- “LangGraph 显著提升性能”：当前本地编排耗时反而更高，且不含真实 LLM；
- “自动识别企业绿洗”：风险输出只是实验性审核信号；
- “开放域工具选择准确率100%”：12条数据是固定离线回归集；
- “实时登记查询”：11,110条数据来自本地静态快照。
