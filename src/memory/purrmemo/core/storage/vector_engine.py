import os
from datetime import datetime
from chromadb import PersistentClient
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from src.utils.config import get_memory_config, get_embedding_model
from ..utils import SingletonMeta

class VectorEngine(metaclass=SingletonMeta):
    def __init__(self):
        config = get_memory_config().get('chromadb', {})
        self.persist_directory = config.get('persist_directory', 'data/memory/chromadb')
        self.collection_name = config.get('collection_name', 'experiences')
        self.graph_collection_name = "graph_nodes"
        self.events_collection_name = "events"
        self.embedding_model_name = get_embedding_model()
        self.client = None
        self.collection = None
        self.graph_collection = None
        self.events_collection = None
        self.embedding_model = None
        self._init_db()
    
    def _init_db(self):
        """初始化向量数据库"""
        os.makedirs(self.persist_directory, exist_ok=True)
        
        self.client = PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.graph_collection = self.client.get_or_create_collection(
            name=self.graph_collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.events_collection = self.client.get_or_create_collection(
            name=self.events_collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
    
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
                'timestamp': timestamp or datetime.now().isoformat(),
                'last_accessed': datetime.now().isoformat(),
                'access_count': 1
            }
            if source_event_id:
                metadata['source_event_id'] = source_event_id
            
            # 先获取现有记录的 access_count（如果存在）
            existing = self.get_experience_by_id(exp_id)
            if existing and 'access_count' in existing.get('metadata', {}):
                metadata['access_count'] = existing['metadata']['access_count'] + 1
            
            self.collection.upsert(
                ids=[exp_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
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
                metadatas=[{"timestamp": timestamp or datetime.now().isoformat()}]
            )
            return True
        except Exception as e:
            print(f"插入事件向量失败: {e}")
            return False
    
    def get_event_by_id(self, event_id):
        """根据 ID 获取事件"""
        try:
            results = self.events_collection.get(ids=[event_id])
            if results['ids']:
                return {
                    'event_id': results['ids'][0],
                    'content': results['documents'][0],
                    'metadata': results['metadatas'][0] if results['metadatas'][0] else {}
                }
            return None
        except Exception as e:
            print(f"获取事件失败: {e}")
            return None

    def search_events_vector(self, query, top_k=200, query_embedding=None):
        """利用 ChromaDB 高效检索事件向量"""
        try:
            if not query_embedding:
                query_embedding = self._get_embedding(query)
            if not query_embedding:
                return []
            
            actual_top_k = min(top_k, self.events_collection.count())
            if actual_top_k == 0:
                return []
                
            results = self.events_collection.query(
                query_embeddings=[query_embedding],
                n_results=actual_top_k
            )
            
            events = []
            for i in range(len(results['ids'][0])):
                similarity = 1.0 - results['distances'][0][i]
                events.append({
                    "id": results['ids'][0][i],
                    "data": {
                        "event_id": results['ids'][0][i],
                        "content": results['documents'][0][i],
                        "timestamp": results['metadatas'][0][i].get('timestamp')
                    },
                    "score": similarity
                })
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
            
            actual_top_k = min(top_k, self.collection.count())
            if actual_top_k == 0:
                return []
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=actual_top_k
            )
            
            experiences = []
            for i in range(len(results['ids'][0])):
                exp_id = results['ids'][0][i]
                content = results['documents'][0][i]
                score = results['distances'][0][i]
                metadata = results['metadatas'][0][i] if results['metadatas'][0][i] else {}
                
                if 1.0 - score >= 0.35:
                    experiences.append({
                        'exp_id': exp_id,
                        'content': content,
                        'score': score,
                        'metadata': metadata
                    })
            
            return experiences
        except Exception as e:
            print(f"搜索经验失败: {e}")
            return []
    
    def get_experience_by_id(self, exp_id):
        """根据 ID 获取经验"""
        try:
            results = self.collection.get(ids=[exp_id])
            if results['ids']:
                return {
                    'exp_id': results['ids'][0],
                    'content': results['documents'][0],
                    'metadata': results['metadatas'][0] if results['metadatas'][0] else {}
                }
            return None
        except Exception as e:
            print(f"获取经验失败: {e}")
            return None
    
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
                metadatas=[{"node_name": node_name}]
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
            
            actual_top_k = min(top_k * 2, self.graph_collection.count())
            if actual_top_k == 0:
                return []
            
            vector_res = self.graph_collection.query(
                query_embeddings=[query_embedding],
                n_results=actual_top_k
            )
            
            nodes = []
            query_lower = query.lower()
            
            for i in range(len(vector_res['ids'][0])):
                node_name = vector_res['documents'][0][i]
                base_score = 1.0 - vector_res['distances'][0][i] 
                boost = 2.0 if query_lower == node_name.lower() else (
                    0.5 if query_lower in node_name.lower() or node_name.lower() in query_lower else 0.0
                )
                
                nodes.append({
                    'node_id': vector_res['ids'][0][i],
                    'node_name': node_name,
                    'score': base_score + boost
                })
            
            nodes.sort(key=lambda x: x['score'], reverse=True)
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
            if not results['ids']:
                return 0
            
            current_time = datetime.now()
            deleted_count = 0
            
            for i, exp_id in enumerate(results['ids']):
                metadata = results['metadatas'][i] if results['metadatas'][i] else {}
                
                if 'last_accessed' in metadata:
                    last_accessed = datetime.fromisoformat(metadata['last_accessed'])
                    if (current_time - last_accessed).days > days_threshold and metadata.get('access_count', 0) < min_access_count:
                        self.collection.delete(ids=[exp_id])
                        deleted_count += 1

            return deleted_count
        except Exception as e:
            print(f"清理经验失败: {e}")
            return 0
