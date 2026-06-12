import threading

import jieba
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

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
        # 真正需要计算向量时，才去加载几十/几百MB的本地模型
        if self._model is None:
            print("⏳ [LazyLoad] 正在加载 SentenceTransformer 模型入显存/内存...")
            # 局部导入，防止阻塞整个文件加载
            from sentence_transformers import SentenceTransformer

            embedding_path = get_embedding_model()
            self._model = SentenceTransformer(embedding_path)
            print("✅ [LazyLoad] 模型加载完毕。")
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts)

    def calculate_similarity(
        self, query_vector: np.ndarray, corpus_matrix: np.ndarray
    ) -> np.ndarray:
        if corpus_matrix is None or len(corpus_matrix) == 0:
            return np.array([])
        query_vector = np.array(query_vector).reshape(1, -1)
        return cosine_similarity(query_vector, corpus_matrix).flatten()
