# 碳信用披露证据助手

面向碳信用披露审核场景的双语 RAG 原型。系统从本地 PDF 中检索可追溯证据，生成带文件与页码引用的回答，辅助人工审核，不替代合规、法律或绿洗判断。

## 项目功能

- 导入中英文碳信用相关 PDF，保留来源文件、物理页码、语言和文档类型；
- 使用本地 `intfloat/multilingual-e5-small` 生成中英文向量；
- 实现 Dense Retrieval、BM25、RRF Hybrid Retrieval；
- 接入 Cross-Encoder Reranker，并与其他检索策略进行对比评估；
- 使用 DeepSeek 仅依据检索证据生成回答；
- 回答使用 `[S1]` 等编号引用，界面可展开查看对应 Chunk 原文；
- 当资料不足时提示“证据不足，需要人工复核”；
- 对“企业是否绿洗”等超出证据边界的问题拒绝作出判断；
- 提供本地 Streamlit 演示界面。

## 系统流程

```text
PDF 文档
  ↓
逐页文本提取与质量检查
  ↓
中英文 Chunk 切分与元数据保留
  ↓
Dense Retrieval + BM25
  ↓
RRF Hybrid Retrieval
  ↓
DeepSeek 证据约束生成
  ↓
带 [S编号]、文件名、页码与 Chunk 预览的回答
```

> Cross-Encoder Reranker 已实现并参与评估；当前 V1 生成层默认使用 Hybrid Retrieval，因为它在初版评估集上取得最高 MRR。

## 数据范围

当前语料为 9 份静态、可追溯 PDF：

- 中文官方规则：`温室气体自愿减排交易管理办法（试行）`；
- 中文官方市场报告：`全国碳市场发展报告（2024）`；
- 中英文企业可持续发展或气候转型披露文件；
- 环境信用会计准则相关企业意见函。

PDF 原始文件、处理中间结果和向量索引仅保存在本地，不提交到 Git 仓库。

## 检索评估

使用 8 条人工标注的中英文问题与正确证据页进行初版评估：

| 方法 | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Dense Retrieval | 0.500 | 0.750 | 0.681 |
| BM25 | 0.750 | 1.000 | 0.875 |
| RRF Hybrid Retrieval | **0.875** | **1.000** | **0.938** |
| Cross-Encoder Reranker | **0.875** | **1.000** | 0.917 |

初版结果表明，Hybrid Retrieval 在该小型评估集上表现最佳。Reranker 在部分细粒度关系问题中出现排序回退，因此保留为可选增强模块，而非默认生成链路。

## 技术栈

- Python 3.10；
- PyTorch + CUDA；
- `sentence-transformers`；
- `intfloat/multilingual-e5-small`；
- `rank-bm25` + `jieba`；
- `BAAI/bge-reranker-base`；
- DeepSeek API：`deepseek-v4-flash`；
- Streamlit；
- `pypdf`、NumPy、JSONL。

## 本地运行

### 1. 配置密钥

在项目根目录创建 `.env`：

```text
DEEPSEEK_API_KEY=你的实际密钥
```

`.env` 已被 Git 忽略，不应提交或分享。

### 2. 启动演示界面

```powershell
python -m streamlit run src\step_13_streamlit_app.py
```

浏览器访问终端显示的本地地址，通常为 `http://localhost:8501`。

### 3. 运行检索评估

```powershell
python src\step_11_evaluate_retrieval.py
```

评估详情会写入 `outputs/retrieval_evaluation.json`。

## 项目结构

```text
src/
  step_01_pdf_loader.py
  step_02_quality_check.py
  step_03_chunker.py
  step_04_chunk_quality_check.py
  step_05_embedding_smoke_test.py
  step_06_build_dense_index.py
  step_07_dense_retriever.py
  step_08_bm25_retriever.py
  step_09_hybrid_retriever.py
  step_10_reranker.py
  step_11_evaluate_retrieval.py
  step_12_answer_generator.py
  step_13_streamlit_app.py

data/
  raw/                 # 本地 PDF，不提交
  processed/           # 逐页文本与 Chunk，不提交
  index/               # 本地向量索引，不提交
  eval/                # 人工标注评估集
```

## 系统边界与局限

- 不实时抓取互联网、交易所或登记机构数据；
- 不对企业是否存在绿洗、违法或合规风险作出自动结论；
- 不将模型生成结果视为法律、财务或审计意见；
- 当前评估集仅包含 8 条人工标注问题，结果用于原型对比，不能视为泛化性能结论；
- 后续可扩展结构化登记记录核对、更多人工标注样本、FastAPI 与 Docker 部署。

## 简历描述参考

构建碳信用披露证据检索 RAG 原型：完成中英文 PDF 解析、Chunk 切分、E5 向量检索、BM25 与 RRF 融合检索，并接入 DeepSeek 实现带页码引用的证据约束问答；在 8 条人工标注中英文评估集上，Hybrid Retrieval 的 MRR 为 0.938，支持 Streamlit 本地演示与证据不足人工复核。