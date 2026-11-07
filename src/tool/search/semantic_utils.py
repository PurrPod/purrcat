import threading

import jieba
import numpy as np

from src.utils.config import get_embedding_model


def hybrid_tokenize(text: str) -> list[str]:
    """
    混合分词器：处理中英文混合语料
    """
    if not text:
        return []

    text = text.lower()
    tokens = jieba.cut_for_search(text)
    return [token for token in tokens if token.strip()]


class LocalEmbeddingSearcher:
    """🌟 重构：懒加载本地大模型"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LocalEmbeddingSearcher, cls).__new__(cls)
                cls._instance._model = None  # 初始时不加载模型
        return cls._instance

    @property
    def model(self):
        # 真正需要计算向量时，才去加载本地 ONNX 模型
        if self._model is None:
            print("⏳ [LazyLoad] 正在加载 ONNX 嵌入模型入内存...")
            # 局部导入，防止阻塞整个文件加载
            from src.utils.local_embedding import get_local_embedder

            self._model = get_local_embedder(get_embedding_model())
            print("✅ [LazyLoad] 模型加载完毕。")
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts)

    def calculate_similarity(
        self, query_vector: np.ndarray, corpus_matrix: np.ndarray
    ) -> np.ndarray:
        if corpus_matrix is None or len(corpus_matrix) == 0:
            return np.array([])
        query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
        corpus = np.asarray(corpus_matrix, dtype=np.float32)
        query_norm = np.linalg.norm(query, axis=1, keepdims=True)
        corpus_norm = np.linalg.norm(corpus, axis=1, keepdims=True)
        query_norm[query_norm == 0] = 1e-12
        corpus_norm[corpus_norm == 0] = 1e-12
        return ((corpus / corpus_norm) @ (query / query_norm).T).ravel()
