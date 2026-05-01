import threading
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


class LocalEmbeddingSearcher:
    """单例模式：全局共享加载的本地小模型，保证线程安全"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LocalEmbeddingSearcher, cls).__new__(cls)
                cls._instance.model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        return cls._instance

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts)

    def calculate_similarity(self, query_vector: np.ndarray, corpus_matrix: np.ndarray) -> np.ndarray:
        query_vector = np.array(query_vector).reshape(1, -1)

        return cosine_similarity(query_vector, corpus_matrix).flatten()