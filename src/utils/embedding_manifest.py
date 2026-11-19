"""嵌入模型的清单、完整性与源解析（不触发下载）。"""

import hashlib
import json
import os

MODEL_NAME = "Xenova/multilingual-e5-small"
# 模型身份标记：目录里存在且内容一致，才认为是可以直接复用的权重
MODEL_TAG = "xenova-multilingual-e5-small-int8-v1"
TAG_FILE = ".model_tag"

# e5 系要求查询与文档使用不同前缀，检索时两侧必须一致
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "

# 自托管镜像基址，需保持 HF 兼容布局：{base}/{repo}/resolve/main/{file}
ENV_MODEL_BASE = "PURRCAT_EMBEDDING_BASE"
DEFAULT_SOURCES = ("https://hf-mirror.com", "https://huggingface.co")

ONNX_FILES = [
    "onnx/model_quantized.onnx",
    "onnx/model.onnx",
    "model.onnx",
]

# 共用的 tokenizer / 配置（与 ORT 推理所需的最小集合）
SHARED_FILES = {
    "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
}

# int8 权重约 118MB；e5-small 的 fp32 约 470MB，仅在镜像缺 int8 时作为后备
MODEL_PROFILES = (
    {
        "onnx/model_quantized.onnx": "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193"
    },
)


def is_model_dir_complete(local_dir: str) -> bool:
    """判断目录是否包含当前模型的 ONNX 与 tokenizer 文件"""
    if not os.path.isdir(local_dir):
        return False
    if not os.path.exists(os.path.join(local_dir, "tokenizer.json")):
        return False
    if _read_tag(local_dir) != MODEL_TAG:
        return False
    # int8 / fp32 / 根目录三种导出布局，任一存在即视为完整
    return any(os.path.exists(os.path.join(local_dir, f)) for f in ONNX_FILES)


def read_model_tag(local_dir: str) -> str:
    """读取目录里的模型身份标记；缺失时返回空串。"""
    return _read_tag(local_dir)


def model_dir_state(local_dir: str) -> str:
    """目录状态：missing / current / partial / outdated。

    - missing：目录不存在或为空，需要自动下载
    - current：标记与文件都匹配当前模型
    - partial：标记是当前模型但文件不全（下载中断），可自动补齐
    - outdated：标记缺失或属于其它模型，交由用户显式更新，不自动覆盖
    """
    if not os.path.isdir(local_dir) or not os.listdir(local_dir):
        return "missing"
    if is_model_dir_complete(local_dir):
        return "current"
    if _read_tag(local_dir) == MODEL_TAG:
        return "partial"
    return "outdated"


def _read_tag(local_dir: str) -> str:
    try:
        with open(os.path.join(local_dir, TAG_FILE), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def write_model_tag(local_dir: str) -> None:
    """下载校验通过后写入模型身份标记。"""
    os.makedirs(local_dir, exist_ok=True)
    with open(os.path.join(local_dir, TAG_FILE), "w", encoding="utf-8") as f:
        f.write(MODEL_TAG)


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
