import os
import threading
from datetime import datetime
from chromadb import Client, PersistentClient
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from src.memory.purrmemo.core.config import VECTOR_DATABASE_CONFIG

class VectorEngine:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VectorEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.persist_directory = VECTOR_DATABASE_CONFIG['persist_directory']
        self.collection_name = VECTOR_DATABASE_CONFIG['collection_name']
        self.graph_collection_name = "graph_nodes"
        self.embedding_model_name = VECTOR_DATABASE_CONFIG.get('embedding_model', 'BAAI/bge-small-zh-v1.5')
        self.client = None
        self.collection = None
        self.graph_collection = None
        self.embedding_model = None
        self._init_db()
        self._initialized = True
    
    def _init_db(self):
        """初始化向量数据库"""
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # 初始化 Chroma 客户端
        self.client = PersistentClient(
            path=self.persist_directory,
            settings=Settings(
                anonymized_telemetry=False
            )
        )
        
        # 获取或创建工作经验集合
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # 获取或创建图谱节点集合
        self.graph_collection = self.client.get_or_create_collection(
            name=self.graph_collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # 加载嵌入模型
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
    
    def _get_embedding(self, text):
        """获取文本的向量表示"""
        if not text:
            return None
        return self.embedding_model.encode(text).tolist()
    
    def insert_experience(self, exp_id, content, timestamp=None, source_event_id=None):
        """插入或更新工作经验
        
        Args:
            exp_id: 经验唯一标识
            content: 经验内容
            timestamp: 时间戳（可选）
            source_event_id: 来源事件 ID（可选）
        """
        try:
            embedding = self._get_embedding(content)
            if not embedding:
                return False
            
            metadata = {}
            if timestamp:
                metadata['timestamp'] = timestamp
            else:
                metadata['timestamp'] = datetime.now().isoformat()
            if source_event_id:
                metadata['source_event_id'] = source_event_id
            
            # 添加最后访问时间
            metadata['last_accessed'] = datetime.now().isoformat()
            # 添加访问次数
            metadata['access_count'] = 1
            
            # 检查经验是否已存在
            existing = self.get_experience_by_id(exp_id)
            if existing:
                # 更新现有经验
                if 'access_count' in existing['metadata']:
                    metadata['access_count'] = existing['metadata']['access_count'] + 1
                
                self.collection.update(
                    ids=[exp_id],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[metadata]
                )
            else:
                # 插入新经验
                self.collection.add(
                    ids=[exp_id],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[metadata]
                )
            return True
        except Exception as e:
            print(f"插入经验失败: {e}")
            return False
    
    def search_experiences(self, query, top_k=5, filters=None):
        """搜索相关工作经验
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 过滤条件（可选）
        """
        try:
            query_embedding = self._get_embedding(query)
            if not query_embedding:
                return []
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filters
            )
            
            # 处理结果
            experiences = []
            for i in range(len(results['ids'][0])):
                exp_id = results['ids'][0][i]
                content = results['documents'][0][i]
                score = results['distances'][0][i]
                metadata = results['metadatas'][0][i] if results['metadatas'][0][i] else {}
                
                # 更新最后访问时间和访问次数
                updated_metadata = metadata.copy()
                updated_metadata['last_accessed'] = datetime.now().isoformat()
                if 'access_count' in updated_metadata:
                    updated_metadata['access_count'] = updated_metadata['access_count'] + 1
                else:
                    updated_metadata['access_count'] = 1
                
                # 更新经验数据
                self.collection.update(
                    ids=[exp_id],
                    metadatas=[updated_metadata]
                )
                
                experience = {
                    'exp_id': exp_id,
                    'content': content,
                    'score': score,
                    'metadata': updated_metadata
                }
                experiences.append(experience)
            
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
        """插入图谱节点到向量库
        
        Args:
            node_id: 节点 ID
            node_name: 节点名称
        """
        try:
            embedding = self._get_embedding(node_name)
            if not embedding:
                return False
            
            self.graph_collection.add(
                ids=[node_id],
                embeddings=[embedding],
                documents=[node_name],
                metadatas=[{"node_name": node_name}]
            )
            return True
        except Exception as e:
            print(f"插入图谱节点失败: {e}")
            return False
    
    def search_graph_nodes(self, query, top_k=5):
        """搜索相关的图谱节点
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
        """
        try:
            query_embedding = self._get_embedding(query)
            if not query_embedding:
                return []
            
            results = self.graph_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            # 处理结果
            nodes = []
            for i in range(len(results['ids'][0])):
                node = {
                    'node_id': results['ids'][0][i],
                    'node_name': results['documents'][0][i],
                    'score': results['distances'][0][i]
                }
                nodes.append(node)
            
            return nodes
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
        """清理过期或不常用的经验
        
        Args:
            days_threshold: 天数阈值，超过该天数未访问的经验会被清理
            min_access_count: 最小访问次数，低于该次数的经验会被清理
        """
        try:
            # 获取所有经验
            results = self.collection.get()
            if not results['ids']:
                return 0
            
            current_time = datetime.now()
            deleted_count = 0
            
            # 检查每个经验
            for i, exp_id in enumerate(results['ids']):
                metadata = results['metadatas'][i] if results['metadatas'][i] else {}
                
                # 检查最后访问时间
                if 'last_accessed' in metadata:
                    last_accessed = datetime.fromisoformat(metadata['last_accessed'])
                    days_since_access = (current_time - last_accessed).days
                    
                    # 检查访问次数
                    access_count = metadata.get('access_count', 0)
                    
                    # 如果超过阈值且访问次数低，删除经验
                    if days_since_access > days_threshold and access_count < min_access_count:
                        self.collection.delete(ids=[exp_id])
                        deleted_count += 1
            
            print(f"清理了 {deleted_count} 个过期或不常用的经验")
            return deleted_count
        except Exception as e:
            print(f"清理经验失败: {e}")
            return 0
