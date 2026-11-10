import os
import threading
from datetime import datetime

from src.utils.config import get_embedding_model
from src.memory.config import (
    CHROMADB_PERSIST_DIRECTORY,
    CHROMADB_COLLECTION_NAME,
    CHROMADB_GRAPH_COLLECTION_NAME,
    CHROMADB_EVENTS_COLLECTION_NAME,
)

from ..clock import days_since, now_iso
from ..filters import clamp_top_k
from ..schema import GRAPH_NODE_CANDIDATE_FACTOR, MIN_EXPERIENCE_SCORE
from ..scoring import graph_node_boost, similarity_from_distance
from ..utils import SingletonMeta


class VectorEngine(metaclass=SingletonMeta):
    """🌟 重构：懒加载 ChromaDB 和 Embedding"""

    def __init__(
        self,
        persist_directory=None,
        collection_name=None,
        graph_collection_name=None,
        events_collection_name=None,
        embedding_model_name=None,
        client=None,
        embedding_model=None,
    ):
        self.persist_directory = (
            persist_directory
            if persist_directory is not None
            else CHROMADB_PERSIST_DIRECTORY
        )
        self.collection_name = (
            collection_name if collection_name is not None else CHROMADB_COLLECTION_NAME
        )
        self.graph_collection_name = (
            graph_collection_name
            if graph_collection_name is not None
            else CHROMADB_GRAPH_COLLECTION_NAME
        )
        self.events_collection_name = (
            events_collection_name
            if events_collection_name is not None
            else CHROMADB_EVENTS_COLLECTION_NAME
        )
        self.embedding_model_name = (
            embedding_model_name
            if embedding_model_name is not None
            else get_embedding_model()
        )

        # 将实例置空
        self._client = client
        self._collection = None
        self._graph_collection = None
        self._events_collection = None
        self._embedding_model = embedding_model

        # 线程锁，防止并发初始化
        self._db_lock = threading.Lock()

        # os.makedirs 放这里没事，但不要建立 DB 连接
        os.makedirs(self.persist_directory, exist_ok=True)

    @property
    def client(self):
        if self._client is None:
            with self._db_lock:
                if self._client is None:  # 双重检查
                    from chromadb import PersistentClient
                    from chromadb.config import Settings

                    print("⏳ [LazyLoad] 初始化 ChromaDB 引擎...")
                    self._client = PersistentClient(
                        path=self.persist_directory,
                        settings=Settings(anonymized_telemetry=False),
                    )
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name, metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    @property
    def graph_collection(self):
        if self._graph_collection is None:
            self._graph_collection = self.client.get_or_create_collection(
                name=self.graph_collection_name, metadata={"hnsw:space": "cosine"}
            )
        return self._graph_collection

    @property
    def events_collection(self):
        if self._events_collection is None:
            self._events_collection = self.client.get_or_create_collection(
                name=self.events_collection_name, metadata={"hnsw:space": "cosine"}
            )
        return self._events_collection

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            # ONNX 推理，兼容原 SentenceTransformer 模型的权重与 tokenizer
            from src.utils.local_embedding import get_local_embedder

            print("[+] 加载 ONNX 嵌入模型...")
            self._embedding_model = get_local_embedder(self.embedding_model_name)
            print("[*] ONNX 嵌入模型加载完毕。")
        return self._embedding_model

    def _get_embedding(self, text):
        """获取文本的向量表示"""
        if not text:
            return None
        return self.embedding_model.encode(text).tolist()

    def insert_experience(self, exp_id, content, timestamp=None, source_event_id=None):
        """插入或更新工作经验"""
        try:
            embedding = self._get_embedding(content)
            if not embedding:
                return False

            # 使用原生 upsert，一行搞定"有则更新，无则插入"
            metadata = {
                "timestamp": timestamp or now_iso(),
                "last_accessed": now_iso(),
                "access_count": 1,
            }
            if source_event_id:
                metadata["source_event_id"] = source_event_id

            # 先获取现有记录的 access_count（如果存在）
            existing = self.get_experience_by_id(exp_id)
            if existing and "access_count" in existing.get("metadata", {}):
                metadata["access_count"] = existing["metadata"]["access_count"] + 1

            self.collection.upsert(
                ids=[exp_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            print(f"插入经验失败: {e}")
            return False

    def insert_event_vector(self, event_id, content, timestamp=None):
        """插入事件向量到 ChromaDB"""
        try:
            embedding = self._get_embedding(content)
            if not embedding:
                return False

            # 使用原生 upsert，一行搞定"有则更新，无则插入"
            self.events_collection.upsert(
                ids=[event_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{"timestamp": timestamp or now_iso()}],
            )
            return True
        except Exception as e:
            print(f"插入事件向量失败: {e}")
            return False

    def _get_record(self, collection, record_id, id_key, label):
        try:
            results = collection.get(ids=[record_id])
            if results["ids"]:
                return {
                    id_key: results["ids"][0],
                    "content": results["documents"][0],
                    "metadata": (
                        results["metadatas"][0] if results["metadatas"][0] else {}
                    ),
                }
            return None
        except Exception as e:
            print(f"获取{label}失败: {e}")
            return None

    def get_event_by_id(self, event_id):
        """根据 ID 获取事件"""
        return self._get_record(self.events_collection, event_id, "event_id", "事件")

    def search_events_vector(self, query, top_k=200, query_embedding=None):
        """利用 ChromaDB 高效检索事件向量"""
        try:
            if not query_embedding:
                query_embedding = self._get_embedding(query)
            if not query_embedding:
                return []

            actual_top_k = clamp_top_k(top_k, self.events_collection.count())
            if actual_top_k == 0:
                return []

            results = self.events_collection.query(
                query_embeddings=[query_embedding], n_results=actual_top_k
            )

            events = []
            for i in range(len(results["ids"][0])):
                similarity = similarity_from_distance(results["distances"][0][i])
                events.append(
                    {
                        "id": results["ids"][0][i],
                        "data": {
                            "event_id": results["ids"][0][i],
                            "content": results["documents"][0][i],
                            "timestamp": results["metadatas"][0][i].get("timestamp"),
                        },
                        "score": similarity,
                    }
                )
            return events
        except Exception as e:
            print(f"ChromaDB 检索事件失败: {e}")
            return []

    def search_experiences(self, query, top_k=5, filters=None, query_embedding=None):
        """搜索相关工作经验"""
        try:
            if not query:
                return []

            if not query_embedding:
                query_embedding = self._get_embedding(query)
            if not query_embedding:
                return []

            actual_top_k = clamp_top_k(top_k, self.collection.count())
            if actual_top_k == 0:
                return []

            results = self.collection.query(
                query_embeddings=[query_embedding], n_results=actual_top_k
            )

            experiences = []
            for i in range(len(results["ids"][0])):
                exp_id = results["ids"][0][i]
                content = results["documents"][0][i]
                distance = results["distances"][0][i]
                metadata = (
                    results["metadatas"][0][i] if results["metadatas"][0][i] else {}
                )

                similarity = similarity_from_distance(distance)
                if similarity >= MIN_EXPERIENCE_SCORE:
                    experiences.append(
                        {
                            "exp_id": exp_id,
                            "content": content,
                            "score": similarity,
                            "metadata": metadata,
                        }
                    )

            return experiences
        except Exception as e:
            print(f"搜索经验失败: {e}")
            return []

    def get_experience_by_id(self, exp_id):
        """根据 ID 获取经验"""
        return self._get_record(self.collection, exp_id, "exp_id", "经验")

    def delete_experience(self, exp_id):
        """删除经验"""
        try:
            self.collection.delete(ids=[exp_id])
            return True
        except Exception as e:
            print(f"删除经验失败: {e}")
            return False

    def get_collection_stats(self):
        """获取集合统计信息"""
        try:
            return self.collection.count()
        except Exception as e:
            print(f"获取集合统计信息失败: {e}")
            return 0

    def insert_graph_node(self, node_id, node_name):
        """插入图谱节点到向量库"""
        try:
            embedding = self._get_embedding(node_name)
            if not embedding:
                return False

            self.graph_collection.upsert(
                ids=[node_id],
                embeddings=[embedding],
                documents=[node_name],
                metadatas=[{"node_name": node_name}],
            )
            return True
        except Exception as e:
            print(f"插入图谱节点失败: {e}")
            return False

    def search_graph_nodes(self, query, top_k=5, query_embedding=None):
        """【混合检索版】图谱节点搜索"""
        try:
            if not query_embedding:
                query_embedding = self._get_embedding(query)
            if not query_embedding:
                return []

            actual_top_k = clamp_top_k(
                top_k * GRAPH_NODE_CANDIDATE_FACTOR, self.graph_collection.count()
            )
            if actual_top_k == 0:
                return []

            vector_res = self.graph_collection.query(
                query_embeddings=[query_embedding], n_results=actual_top_k
            )

            nodes = []

            for i in range(len(vector_res["ids"][0])):
                node_name = vector_res["documents"][0][i]
                base_score = similarity_from_distance(vector_res["distances"][0][i])
                boost = graph_node_boost(query, node_name)

                nodes.append(
                    {
                        "node_id": vector_res["ids"][0][i],
                        "node_name": node_name,
                        "score": base_score + boost,
                    }
                )

            nodes.sort(key=lambda x: x["score"], reverse=True)
            return nodes[:top_k]

        except Exception as e:
            print(f"搜索图谱节点失败: {e}")
            return []

    def get_graph_collection_stats(self):
        """获取图谱节点集合统计信息"""
        try:
            return self.graph_collection.count()
        except Exception as e:
            print(f"获取图谱节点集合统计信息失败: {e}")
            return 0

    def cleanup_old_experiences(self, days_threshold=30, min_access_count=2):
        """清理过期或不常用的经验"""
        try:
            results = self.collection.get()
            if not results["ids"]:
                return 0

            current_time = datetime.now()
            deleted_count = 0

            for i, exp_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results["metadatas"][i] else {}

                if "last_accessed" in metadata:
                    age_days = days_since(metadata["last_accessed"], current_time)
                    if (
                        age_days > days_threshold
                        and metadata.get("access_count", 0) < min_access_count
                    ):
                        self.collection.delete(ids=[exp_id])
                        deleted_count += 1

            return deleted_count
        except Exception as e:
            print(f"清理经验失败: {e}")
            return 0
