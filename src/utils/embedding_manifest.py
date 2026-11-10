"""嵌入模型的清单、完整性与源解析（不触发下载）。"""

import hashlib
import json
import os

# 原 sentence-transformers 仓库自带 onnx/model.onnx（同一份权重），无需换模型
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# 自托管镜像基址，需保持 HF 兼容布局：{base}/{repo}/resolve/main/{file}
ENV_MODEL_BASE = "PURRCAT_EMBEDDING_BASE"
DEFAULT_SOURCES = ("https://hf-mirror.com", "https://huggingface.co")

ONNX_FILES = [
    "onnx/model_quint8_avx2.onnx",
    "onnx/model.onnx",
    "model.onnx",
]

# 共用的 tokenizer / 配置（与 ORT 推理所需的最小集合）
SHARED_FILES = {
    "tokenizer.json": "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8",
    "tokenizer_config.json": "5036ea374ffedd706e3bef33e2e0d6953cb868ef8a490e76e32ba0faa37a6b9b",
    "config.json": "6300193cb75e01cf80c96decef7187dfb33094d97cc1490b7ead6ff134476e4e",
    "special_tokens_map.json": "378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d",
    "sentence_bert_config.json": "70f4448f31320443fe3557cacea5abf2dcc4915dda8c80646bec9f3bb0aa5a1f",
}

# 优先 int8（约 113MB，检索效果几乎无损）；镜像缺 int8 时退回 fp32（约 448MB）
MODEL_PROFILES = (
    {
        "onnx/model_quint8_avx2.onnx": "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f"
    },
    {
        "onnx/model.onnx": "10f7a088420252b26caf819236ca2c9d2987afd0fc06fec7553b542a5655a05a"
    },
)


def is_model_dir_complete(local_dir: str) -> bool:
    """判断目录是否包含 ONNX 模型与 tokenizer 文件"""
    if not os.path.isdir(local_dir):
        return False
    if not os.path.exists(os.path.join(local_dir, "tokenizer.json")):
        return False
    # int8 / fp32 / 根目录三种导出布局，任一存在即视为完整
    return any(os.path.exists(os.path.join(local_dir, f)) for f in ONNX_FILES)


def expected_files(profile: dict) -> dict:
    return {**profile, **SHARED_FILES}


def resolve_sources(endpoint: str | None, env_value: str | None = None) -> list:
    if endpoint:
        return [endpoint]
    return ([env_value] if env_value else []) + list(DEFAULT_SOURCES)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_matches(path: str, expected: str) -> bool:
    return os.path.exists(path) and sha256_file(path) == expected


def read_max_seq_length(model_dir: str, default: int) -> int:
    """读取 SentenceTransformer 实际截断长度（通常 128）。"""
    for filename, key in (
        ("sentence_bert_config.json", "max_seq_length"),
        ("tokenizer_config.json", "model_max_length"),
    ):
        config_path = os.path.join(model_dir, filename)
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                value = int(json.load(f).get(key))
        except (OSError, TypeError, ValueError):
            continue
        # 部分 tokenizer 配置会写成 1e30 之类的“无限长”，需要兜底到模型上限
        if 0 < value <= 4096:
            return value
    return default
