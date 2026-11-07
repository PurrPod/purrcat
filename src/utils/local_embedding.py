"""本地 ONNX 嵌入推理。

用 onnxruntime + tokenizers 复现 SentenceTransformer 的编码流程，
避免把 torch / transformers / sentence-transformers 打进安装包。
模型权重与 tokenizer 由 embedding_setup 下载到数据目录。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Iterable, List, Sequence

import numpy as np

_EMBEDDER_CACHE: dict[str, "LocalEmbedder"] = {}
_EMBEDDER_LOCK = threading.Lock()

_ONNX_CANDIDATES = (
    os.path.join("onnx", "model.onnx"),
    os.path.join("onnx", "model_quint8_avx2.onnx"),
    "model.onnx",
)


def _resolve_onnx_path(model_dir: str) -> str:
    for rel in _ONNX_CANDIDATES:
        path = os.path.join(model_dir, rel)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"未找到 ONNX 模型文件，请重新下载嵌入模型（目录: {model_dir}）"
    )


class LocalEmbedder:
    """与 SentenceTransformer.encode 保持一致的本地 ONNX 编码器。"""

    def __init__(self, model_dir: str, max_length: int = 512):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.model_dir = model_dir
        self._max_length = self._resolve_max_length(model_dir, max_length)
        self._tokenizer = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        # tokenizer.json 可能自带 padding 配置，必须关闭后由本类手动 batch padding，
        # 否则 pad token 会被当成有效 token，导致向量严重偏移
        self._tokenizer.no_padding()
        self._tokenizer.enable_truncation(max_length=self._max_length)

        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        self._session = ort.InferenceSession(
            _resolve_onnx_path(model_dir),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {item.name for item in self._session.get_inputs()}
        output_names = [item.name for item in self._session.get_outputs()]
        self._output_name = (
            "last_hidden_state"
            if "last_hidden_state" in output_names
            else output_names[0]
        )
        self._dim: int | None = None

    @staticmethod
    def _resolve_max_length(model_dir: str, default: int) -> int:
        # sentence_bert_config.json 才是 SentenceTransformer 实际截断长度（通常 128）
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

    def _encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        encodings = self._tokenizer.encode_batch(list(texts))
        max_len = max(len(enc.ids) for enc in encodings)

        input_ids = np.zeros((len(encodings), max_len), dtype=np.int64)
        attention_mask = np.zeros((len(encodings), max_len), dtype=np.int64)
        for row, enc in enumerate(encodings):
            length = len(enc.ids)
            input_ids[row, :length] = enc.ids
            attention_mask[row, :length] = enc.attention_mask

        feeds = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run([self._output_name], feeds)[0]
        if outputs.ndim == 2:
            # 少数导出版本直接输出 sentence_embedding
            return np.asarray(outputs, dtype=np.float32)

        # 与 SentenceTransformer 的 mean pooling 完全一致
        mask = attention_mask[..., None].astype(np.float32)
        summed = (outputs * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1e-9, None)
        return np.asarray(summed / counts, dtype=np.float32)

    def encode(
        self,
        texts: str | Iterable[str],
        batch_size: int = 32,
    ) -> np.ndarray:
        """编码文本。传入 str 返回 (dim,)，传入列表返回 (n, dim)。"""
        single = isinstance(texts, str)
        items: List[str] = [texts] if single else list(texts)
        if not items:
            return np.zeros((0, self._dim or 0), dtype=np.float32)

        vectors: list[np.ndarray] = []
        for start in range(0, len(items), max(1, batch_size)):
            batch = items[start : start + max(1, batch_size)]
            vectors.append(self._encode_batch(batch))

        matrix = np.vstack(vectors)
        self._dim = int(matrix.shape[1])
        return matrix[0] if single else matrix


def get_local_embedder(model_dir: str) -> LocalEmbedder:
    """按目录缓存编码器，避免重复加载 ONNX 模型。"""
    key = os.path.abspath(model_dir)
    with _EMBEDDER_LOCK:
        embedder = _EMBEDDER_CACHE.get(key)
        if embedder is None:
            embedder = LocalEmbedder(model_dir)
            _EMBEDDER_CACHE[key] = embedder
        return embedder
