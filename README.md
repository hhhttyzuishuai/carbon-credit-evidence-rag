# 碳信用披露证据助手

面向碳信用披露审核场景的双语 RAG 原型。系统从本地 PDF 中检索可追溯证据，生成带文件与页码引用的回答，辅助人工审核，不替代合规、法律或绿洗判断。

## 项目功能

- 导入中英文碳信用相关 PDF，保留来源文件、物理页码、语言和文档类型；
- 使用本地 `intfloat/multilingual-e5-small` 生成中英文向量；
- 实现 Dense Retrieval、BM25、RRF Hybrid Retrieval；
- 接入 Cross-Encoder Reranker，并与其他检索策略进行对比评估；
- 使用 DeepSeek 仅依据检索证据生成回答；
- 回答使用 `[S1]` 等编号引用，界面可展开查看对应 Chunk 原文；
- 支持按 Project ID 精确查询本地登记记录快照，返回登记机构、项目状态、已签发/已注销/剩余数量，以及 Excel 工作表与行号；
- 当资料不足时提示“证据不足，需要人工复核”；
- 对“企业是否绿洗”等超出证据边界的问题拒绝作出判断；
- 提供本地 Streamlit 演示界面。

## V3 风险审核辅助

- 基于本地登记记录和用户提供的声明字段，构造结构化审核特征；
- 在当前 Python 3.10 环境中复现结构化 XGBoost 二分类实验；
- 使用 XGBoost 原生 TreeSHAP 输出特征贡献，辅助人工理解模型信号；
- `low_risk`、`high_risk`、`review_required` 是审核决策状态，不是模型原生三分类标签；
- 当前演示环境默认输出 `review_required`：缺少可比数量、单位、核对口径或来源时，不调用模型评分；
- 模型输出仅为实验性风险信号，不构成绿洗、违法、合规或法律结论。

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
RRF Hybrid Retrieval（召回 20 条候选）
  ↓
Cross-Encoder Reranker（精排后保留前 5 条）
  ↓
DeepSeek 证据约束生成
  ↓
带 [S编号]、文件名、页码与 Chunk 预览的回答
```

> 当前 V1 问答链路默认使用 `Hybrid Retrieval → Cross-Encoder Reranker → DeepSeek`。
>
> 在 50 条人工标注双语评估集中，Reranker 的综合检索效果最佳；候选数固定为 20。

## 结构化登记记录核对（V2）

除 PDF 证据检索外，系统还读取本地自愿碳抵消项目登记记录 Excel 快照。

`Project ID`
  ↓
规范化（去除首尾空格、统一转为大写）
  ↓
精确匹配本地项目索引
  ↓
返回登记机构、项目状态、已签发/已注销/剩余数量
  ↓
展示来源工作簿、工作表与 Excel 行号

当前使用 `Dim_C_Voluntary-Registry-Offsets-Database--v2026-02.xlsx` 的 `PROJECTS` 工作表，共导出 11,110 条项目记录。结构化查询只做精确字段核对，不让大模型计算、猜测或模糊匹配项目数据。

## 数据范围

当前语料为 9 份静态、可追溯 PDF：

- 中文官方规则：`温室气体自愿减排交易管理办法（试行）`；
- 中文官方市场报告：`全国碳市场发展报告（2024）`；
- 中英文企业可持续发展或气候转型披露文件；
- 环境信用会计准则相关企业意见函。

PDF 原始文件、处理中间结果和向量索引仅保存在本地，不提交到 Git 仓库。

## 检索评估

使用 50 条人工标注的中英文问题进行评估。每条问题均标注可验证的来源文件与物理页码；覆盖中文官方规则与市场报告、中英文企业披露，以及环境信用会计意见函。

| 方法 | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Dense Retrieval | 0.540 | 0.720 | 0.656 |
| BM25 | 0.680 | 0.880 | 0.785 |
| RRF Hybrid Retrieval | 0.580 | 0.820 | 0.722 |
| Cross-Encoder Reranker | **0.780** | **0.980** | **0.863** |

为验证候选池大小的影响，进一步比较了 Reranker 的候选数：

| Reranker 候选数 | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| 20 | **0.780** | **0.980** | **0.863** |
| 50 | 0.780 | 0.960 | 0.859 |

实验显示，扩大候选池未提升当前评估集效果，反而引入相似但不相关的文本。因此系统保留 `candidate_k=20`，在检索质量与推理开销之间取得当前配置下更合适的平衡。

上述结论仅适用于当前 9 份静态 PDF 与 50 条人工标注评估集，不代表通用领域性能。

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
- `pandas` + `openpyxl`；

## 本地运行

### 1. 安装依赖

先根据本机的 GPU、CUDA 与操作系统安装 PyTorch；本项目开发环境已验证 CUDA 可用。

随后安装其余项目依赖：

```powershell
python -m pip install -r requirements.txt
```

### 2. 配置密钥

在项目根目录创建 `.env`：

```text
DEEPSEEK_API_KEY=你的实际密钥
```

`.env` 已被 Git 忽略，不应提交或分享。

### 3. 启动演示界面

```powershell
python -m streamlit run src\step_13_streamlit_app.py
```

浏览器访问终端显示的本地地址，通常为 `http://localhost:8501`。

### 4. 运行检索评估

```powershell
python src\step_11_evaluate_retrieval.py
```

评估详情会写入 `outputs/retrieval_evaluation.json`。

### 5. 构建并查询登记记录索引

首次使用或更换 Excel 数据版本后，先导出结构化项目记录：

```powershell
python src\step_14_registry_loader.py  # 精确查询项目字段，并显示 Excel 溯源位置
python src\step_15_registry_lookup.py --project-id ACR102  # 精确查询项目字段，并显示 Excel 溯源位置


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
  step_14_registry_loader.py
  step_15_registry_lookup.py

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
- 当前评估集包含 50 条人工标注问题，适用于当前原型的对比实验，不能视为通用领域性能结论；
- 后续可扩展结构化登记记录核对、更多人工标注样本、FastAPI 与 Docker 部署。
- 登记记录来自本地 `v2026-02` Excel 快照，不能代表登记机构的实时项目状态；

## 简历描述参考

构建碳信用披露证据检索 RAG 原型：完成 9 份中英文 PDF 的页码级溯源解析、Chunk 切分、E5 向量检索、BM25 与 RRF 召回，并接入 Cross-Encoder 精排及 DeepSeek 证据约束问答。在 50 条人工标注双语评估集上，精排链路取得 Hit@1 0.780、Hit@3 0.980、MRR 0.863；实现 Streamlit 证据展示、引用编号校验与“证据不足，需人工复核”的安全边界。