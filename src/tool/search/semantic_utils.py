import threading

import jieba
import numpy as np
from sentence_transformers import SentenceTransformer
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
    """单例模式：全局共享加载的本地小模型，保证线程安全"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LocalEmbeddingSearcher, cls).__new__(cls)
                # 使用 get_embedding_model() 获取嵌入模型路径（默认使用本地 embedding 文件夹）
                embedding_path = get_embedding_model()
                cls._instance.model = SentenceTransformer(embedding_path)
        return cls._instance

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts)

    def calculate_similarity(
        self, query_vector: np.ndarray, corpus_matrix: np.ndarray
    ) -> np.ndarray:
        query_vector = np.array(query_vector).reshape(1, -1)

        return cosine_similarity(query_vector, corpus_matrix).flatten()
