import torch
from sentence_transformers import SentenceTransformer


# 选定的中英文通用本地 Embedding 模型。
MODEL_NAME = "intfloat/multilingual-e5-small"

# CUDA 可用时使用 GPU，否则自动回退到 CPU。
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# E5 模型要求：查询以 query: 开头，资料文本以 passage: 开头。
query = "query: 温室气体自愿减排项目申请登记需要满足哪些条件？"

passages = [
    (
        "passage: 申请登记的温室气体自愿减排项目应当具备真实性、"
        "唯一性和额外性，并属于项目方法学支持领域。"
    ),
    (
        "passage: 中国平安发布了 2024 年可持续发展报告，"
        "介绍了企业环境与社会责任相关工作。"
    ),
]


if __name__ == "__main__":
    print(f"加载模型：{MODEL_NAME}")
    print(f"运行设备：{DEVICE}")

    # 第一次运行会下载模型文件；后续会直接使用本地缓存。
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)

    # 归一化后，向量点积等于余弦相似度。
    embeddings = model.encode(
        [query, *passages],
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    # 第一个向量是查询，后两个是候选资料文本。
    scores = embeddings[0] @ embeddings[1:].T

    print(f"向量形状：{embeddings.shape}")
    print(f"与相关规则文本的相似度：{scores[0]:.4f}")
    print(f"与无关企业文本的相似度：{scores[1]:.4f}")