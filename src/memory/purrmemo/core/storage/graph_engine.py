import os
import pickle
import hashlib
import threading
from datetime import datetime
import networkx as nx
from src.memory.purrmemo.core.config import GRAPH_DATABASE_CONFIG
from src.memory.purrmemo.core.storage.vector_engine import VectorEngine

class GraphEngine:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GraphEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._rw_lock = threading.RLock()
        self.graph_path = GRAPH_DATABASE_CONFIG['graph_path']
        self.min_confidence = GRAPH_DATABASE_CONFIG['min_confidence']
        self.graph = None
        self.vector_engine = None
        try:
            self.vector_engine = VectorEngine()
        except Exception:
            print("向量引擎依赖未安装，将在无向量搜索模式下运行")
        self._init_graph()
        self._initialized = True
    
    def _init_graph(self):
        """初始化图谱"""
        os.makedirs(os.path.dirname(self.graph_path), exist_ok=True)
        
        # 尝试加载已有的图谱
        try:
            if os.path.exists(self.graph_path):
                with open(self.graph_path, 'rb') as f:
                    self.graph = pickle.load(f)
            else:
                self.graph = nx.DiGraph()
        except Exception as e:
            print(f"加载图谱失败: {e}")
            self.graph = nx.DiGraph()
    
    def _generate_edge_id(self, source_node_id, target_node_id, relation_meaning):
        """生成边的唯一标识"""
        key = f"{source_node_id}_{target_node_id}_{relation_meaning}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def add_node(self, node_id, name, vector=None):
        """添加节点
        
        Args:
            node_id: 节点唯一标识
            name: 节点名称
            vector: 节点向量（可选）
        """
        try:
            with self._rw_lock:
                if not self.graph.has_node(node_id):
                    self.graph.add_node(node_id, name=name, vector=vector)
                    # 同时将节点插入到向量库中（如果向量引擎可用）
                    if self.vector_engine:
                        self.vector_engine.insert_graph_node(node_id, name)
            return True
        except Exception as e:
            print(f"添加节点失败: {e}")
            return False
    
    def add_relation(self, source_node_id, target_node_id, relation_meaning, confidence=0.5, source_event_id=None):
        """添加或更新关系
        
        Args:
            source_node_id: 源节点 ID
            target_node_id: 目标节点 ID
            relation_meaning: 关系含义
            confidence: 置信度（0.0-1.0）
            source_event_id: 来源事件 ID（可选）
        """
        try:
            # 确保源节点和目标节点存在
            with self._rw_lock:
                if not self.graph.has_node(source_node_id):
                    return False
                if not self.graph.has_node(target_node_id):
                    return False
                
                edge_id = self._generate_edge_id(source_node_id, target_node_id, relation_meaning)
                timestamp = datetime.now().isoformat()
                
                # 检查是否已存在该关系
                if self.graph.has_edge(source_node_id, target_node_id):
                    # 更新关系
                    self.graph[source_node_id][target_node_id].update({
                        'edge_id': edge_id,
                        'relation_meaning': relation_meaning,
                        'confidence': confidence,
                        'updated_at': timestamp,
                        'source_event_id': source_event_id
                    })
                else:
                    # 添加新关系
                    self.graph.add_edge(source_node_id, target_node_id, 
                        edge_id=edge_id,
                        relation_meaning=relation_meaning,
                        confidence=confidence,
                        created_at=timestamp,
                        updated_at=timestamp,
                        source_event_id=source_event_id
                    )
            return True
        except Exception as e:
            print(f"添加关系失败: {e}")
            return False
    
    def reinforce_relation(self, source_node_id, target_node_id, relation_meaning, increment=0.1):
        """强化关系（增加置信度）
        
        Args:
            source_node_id: 源节点 ID
            target_node_id: 目标节点 ID
            relation_meaning: 关系含义
            increment: 置信度增量
        """
        try:
            with self._rw_lock:
                if not self.graph.has_edge(source_node_id, target_node_id):
                    return False
                
                edge_data = self.graph[source_node_id][target_node_id]
                if edge_data.get('relation_meaning') == relation_meaning:
                    # 增加置信度，但不超过 1.0
                    new_confidence = min(1.0, edge_data['confidence'] + increment)
                    edge_data['confidence'] = new_confidence
                    edge_data['updated_at'] = datetime.now().isoformat()
                    return True
            return False
        except Exception as e:
            print(f"强化关系失败: {e}")
            return False
    
    def weaken_relation(self, source_node_id, target_node_id, relation_meaning, decrement=0.1):
        """削弱关系（降低置信度）
        
        Args:
            source_node_id: 源节点 ID
            target_node_id: 目标节点 ID
            relation_meaning: 关系含义
            decrement: 置信度减量
        """
        try:
            with self._rw_lock:
                if not self.graph.has_edge(source_node_id, target_node_id):
                    return False
                
                edge_data = self.graph[source_node_id][target_node_id]
                if edge_data.get('relation_meaning') == relation_meaning:
                    # 降低置信度，但不低于最小阈值
                    new_confidence = max(self.min_confidence, edge_data['confidence'] - decrement)
                    edge_data['confidence'] = new_confidence
                    edge_data['updated_at'] = datetime.now().isoformat()
                    return True
            return False
        except Exception as e:
            print(f"削弱关系失败: {e}")
            return False
    
    def get_node(self, node_id):
        """获取节点"""
        try:
            with self._rw_lock:
                if self.graph.has_node(node_id):
                    node_data = self.graph.nodes[node_id]
                    return {
                        'node_id': node_id,
                        'name': node_data.get('name'),
                        'vector': node_data.get('vector')
                    }
            return None
        except Exception as e:
            print(f"获取节点失败: {e}")
            return None
    
    def get_relation(self, source_node_id, target_node_id):
        """获取关系"""
        try:
            with self._rw_lock:
                if self.graph.has_edge(source_node_id, target_node_id):
                    edge_data = self.graph[source_node_id][target_node_id]
                    return {
                        'edge_id': edge_data.get('edge_id'),
                        'source_node_id': source_node_id,
                        'target_node_id': target_node_id,
                        'relation_meaning': edge_data.get('relation_meaning'),
                        'confidence': edge_data.get('confidence'),
                        'created_at': edge_data.get('created_at'),
                        'updated_at': edge_data.get('updated_at'),
                        'source_event_id': edge_data.get('source_event_id')
                    }
            return None
        except Exception as e:
            print(f"获取关系失败: {e}")
            return None
    
    def get_relations_by_node(self, node_id, direction='out'):
        """获取节点的关系
        
        Args:
            node_id: 节点 ID
            direction: 方向 ('out' 出边, 'in' 入边, 'all' 所有边)
        """
        try:
            relations = []
            
            with self._rw_lock:
                if direction in ['out', 'all']:
                    # 获取出边
                    for neighbor in self.graph.neighbors(node_id):
                        edge_data = self.graph[node_id][neighbor]
                        # 过滤低置信度的关系
                        if edge_data.get('confidence', 0) >= self.min_confidence:
                            relations.append({
                                'edge_id': edge_data.get('edge_id'),
                                'source_node_id': node_id,
                                'target_node_id': neighbor,
                                'relation_meaning': edge_data.get('relation_meaning'),
                                'confidence': edge_data.get('confidence'),
                                'created_at': edge_data.get('created_at'),
                                'updated_at': edge_data.get('updated_at'),
                                'source_event_id': edge_data.get('source_event_id')
                            })
                
                if direction in ['in', 'all']:
                    # 获取入边
                    for predecessor in self.graph.predecessors(node_id):
                        edge_data = self.graph[predecessor][node_id]
                        # 过滤低置信度的关系
                        if edge_data.get('confidence', 0) >= self.min_confidence:
                            relations.append({
                                'edge_id': edge_data.get('edge_id'),
                                'source_node_id': predecessor,
                                'target_node_id': node_id,
                                'relation_meaning': edge_data.get('relation_meaning'),
                                'confidence': edge_data.get('confidence'),
                                'created_at': edge_data.get('created_at'),
                                'updated_at': edge_data.get('updated_at'),
                                'source_event_id': edge_data.get('source_event_id')
                            })
            
            return relations
        except Exception as e:
            print(f"获取节点关系失败: {e}")
            return []
    
    def _save_graph(self):
        """保存图谱到文件"""
        with self._rw_lock:
            try:
                with open(self.graph_path, 'wb') as f:
                    pickle.dump(self.graph, f)
            except Exception as e:
                print(f"保存图谱失败: {e}")
    
    def get_graph_stats(self):
        """获取图谱统计信息"""
        try:
            with self._rw_lock:
                return {
                    'nodes': self.graph.number_of_nodes(),
                    'edges': self.graph.number_of_edges()
                }
        except Exception as e:
            print(f"获取图谱统计信息失败: {e}")
            return {'nodes': 0, 'edges': 0}
    
    def decay_edges(self, edges_to_update):
        """批量衰减边的置信度
        
        Args:
            edges_to_update: 需要更新的边列表，每个元素包含 source_node_id, target_node_id, new_confidence
        
        Returns:
            成功更新的边数量
        """
        try:
            with self._rw_lock:
                updated_count = 0
                for edge in edges_to_update:
                    source_node_id = edge['source_node_id']
                    target_node_id = edge['target_node_id']
                    new_confidence = edge['new_confidence']
                    
                    if self.graph.has_edge(source_node_id, target_node_id):
                        edge_data = self.graph[source_node_id][target_node_id]
                        edge_data['confidence'] = new_confidence
                        edge_data['updated_at'] = datetime.now().isoformat()
                        updated_count += 1
                
                return updated_count
        except Exception as e:
            print(f"衰减边失败: {e}")
            return 0
