import os
import json
from datetime import datetime, timedelta
import threading
from .config import RAG_CONFIG
from .storage.event_engine import EventEngine
from .storage.vector_engine import VectorEngine
from .storage.graph_engine import GraphEngine
from concurrent.futures import ThreadPoolExecutor, as_completed

class RAGSearchTool:
    def __init__(self):
        self.event_engine = EventEngine()
        
        try:
            self.vector_engine = VectorEngine()
        except Exception:
            self.vector_engine = None
            print("VectorEngine 不可用，将无法检索经验库")

        try:
            self.graph_engine = GraphEngine()
        except Exception:
            self.graph_engine = None
            print("GraphEngine 不可用，将无法检索图谱库")

    def search_memory_api(self, query: str, filters: dict = None):
        """统一检索接口

        Args:
            query: 查询文本
            filters: 过滤条件（可选）

        Returns:
            结构化的 Markdown 上下文
        """
        # 并发检索三路
        events_results = []
        experiences_results = []
        graph_results = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_source = {
                executor.submit(self._search_events, query, filters): 'events',
                executor.submit(self._search_experiences, query, filters): 'experiences',
                executor.submit(self._search_graph, query, filters): 'graph'
            }

            events_warning = ""
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    result = future.result()
                    if source == 'events':
                        if isinstance(result, dict):
                            events_warning = result.get('warning', '')
                            events_results = result.get('events', [])
                        else:
                            events_results = result
                    elif source == 'experiences':
                        experiences_results = result
                    elif source == 'graph':
                        graph_results = result
                except Exception as e:
                    print(f"检索 {source} 失败: {e}")

        markdown_context = self._format_results(events_results, experiences_results, graph_results, events_warning)

        return markdown_context

    def _search_events(self, query: str, filters: dict = None):
        """检索事件库
        
        Returns:
            dict: {"events": [...], "warning": "..."} 
            warning 为空表示无降级查询，有内容表示使用了降级查询并说明原因
        """
        try:
            had_time_filter = filters and 'time_range' in filters
            start_time = None
            end_time = None
            
            if filters and 'time_range' in filters:
                start_time, end_time = filters['time_range']
                events = self.event_engine.get_events_by_time_range(
                    start_time=start_time,
                    end_time=end_time,
                    limit=RAG_CONFIG['top_k_events'] * 2
                )
            else:
                events = self.event_engine.get_latest_events(
                    limit=RAG_CONFIG['top_k_events'] * 2
                )
            
            fallback_warning = ""
            
            if query and self.vector_engine:
                query_vector = self.vector_engine._get_embedding(query)
                if query_vector:
                    import numpy as np
                    similar_events = []
                    for event in events:
                        if event.get('vector'):
                            event_vector = event['vector']
                            similarity = np.dot(query_vector, event_vector) / (
                                np.linalg.norm(query_vector) * np.linalg.norm(event_vector)
                            )
                            event['similarity'] = similarity
                            similar_events.append(event)
                    
                    similar_events.sort(key=lambda x: x.get('similarity', 0), reverse=True)
                    
                    if filters and 'threshold' in filters:
                        threshold = filters['threshold']
                        similar_events = [e for e in similar_events if e.get('similarity', 0) >= threshold]
                    
                    results = similar_events[:RAG_CONFIG['top_k_events']]
                    
                    if not results and had_time_filter:
                        fallback_events = self.event_engine.get_latest_events(
                            limit=RAG_CONFIG['top_k_events']
                        )
                        for fe in fallback_events:
                            if fe.get('vector'):
                                fe['similarity'] = np.dot(query_vector, fe['vector']) / (
                                    np.linalg.norm(query_vector) * np.linalg.norm(fe['vector'])
                                )
                            else:
                                fe['similarity'] = 0.0
                        
                        fallback_events.sort(key=lambda x: x.get('similarity', 0), reverse=True)
                        fallback_warning = f"**当前筛选条件没有符合条件的事件，以下是一些相关的结果：**\n\n"
                        results = fallback_events[:RAG_CONFIG['top_k_events']]
                    
                    return {"events": results, "warning": fallback_warning}
            
            if not events and had_time_filter:
                fallback_events = self.event_engine.get_latest_events(
                    limit=RAG_CONFIG['top_k_events']
                )
                fallback_warning = f"**当前筛选条件没有符合条件的事件，以下是一些相关的结果：**\n\n"
                return {"events": fallback_events, "warning": fallback_warning}
            
            return {"events": events, "warning": ""}
        except Exception as e:
            print(f"检索事件失败: {e}")
            return {"events": [], "warning": ""}

    def _search_experiences(self, query: str, filters: dict = None):
        """检索经验库"""
        try:
            if not self.vector_engine:
                return []
            
            experiences = self.vector_engine.search_experiences(
                query=query,
                top_k=RAG_CONFIG['top_k_experiences'],
                filters=filters
            )
            return experiences
        except Exception as e:
            print(f"检索经验失败: {e}")
            return []

    def _search_graph(self, query: str, filters: dict = None):
        """检索图谱库 - 向量寻址 Node -> 一跳游走提取 Edge"""
        try:
            if not self.graph_engine:
                return []
                
            graph_stats = self.graph_engine.get_graph_stats()
            if graph_stats['nodes'] == 0:
                return []

            results = []

            # 使用向量检索查找相关节点（如果向量引擎可用）
            if hasattr(self.graph_engine, 'vector_engine') and self.graph_engine.vector_engine:
                similar_nodes = self.graph_engine.vector_engine.search_graph_nodes(query, top_k=5)
            else:
                # 无向量引擎时返回空结果
                return []
            
            # 处理向量检索结果
            for node_info in similar_nodes:
                node_id = node_info['node_id']
                # 一跳游走提取 Edge
                relations = self.graph_engine.get_relations_by_node(node_id, direction='all')
                for relation in relations:
                    # 过滤低置信度 Edge
                    if relation['confidence'] >= self.graph_engine.min_confidence:
                        target_node = self.graph_engine.get_node(relation['target_node_id'])
                        target_name = target_node['name'] if target_node else '未知'

                        source_node = self.graph_engine.get_node(relation['source_node_id'])
                        source_name = source_node['name'] if source_node else '未知'

                        # 翻译为自然语言
                        relation_desc = f"{source_name} {relation['relation_meaning']} {target_name}"
                        results.append({
                            'source': source_name,
                            'relation': relation['relation_meaning'],
                            'target': target_name,
                            'confidence': relation['confidence'],
                            'description': relation_desc
                        })

            # 按置信度排序
            results.sort(key=lambda x: x['confidence'], reverse=True)
            return results[:RAG_CONFIG['top_k_graph_nodes']]
        except Exception as e:
            print(f"检索图谱失败: {e}")
            return []

    def _format_results(self, events, experiences, graph_results, events_warning=""):
        """将结果格式化为 Markdown"""
        markdown_parts = []

        if events_warning:
            markdown_parts.append(events_warning)

        if events:
            markdown_parts.append("## 历史事件")
            for event in events:
                markdown_parts.append(f"- [{event['timestamp']}] {event['content']}")
            markdown_parts.append("")

        if experiences:
            markdown_parts.append("## 工作经验")
            for exp in experiences:
                score = 1.0 - exp['score']
                markdown_parts.append(f"- [{score:.2f}] {exp['content']}")
            markdown_parts.append("")

        if graph_results:
            markdown_parts.append("## 知识图谱")
            for result in graph_results:
                markdown_parts.append(f"- {result['description']} (置信度: {result['confidence']:.2f})")
            markdown_parts.append("")

        if not markdown_parts:
            markdown_parts.append("## 检索结果")
            markdown_parts.append("没有找到相关信息")

        return "\n".join(markdown_parts)


class ForgetfulnessManager:
    """遗忘管理器 - 定时清理长时间未强化的关系"""

    def __init__(self, graph_engine, min_confidence=0.3, decay_rate=0.05):
        self.graph_engine = graph_engine
        self.min_confidence = min_confidence
        self.decay_rate = decay_rate

    def decay_unreinforced_edges(self, days_threshold=7):
        """衰减长时间未强化的边

        Args:
            days_threshold: 未强化天数阈值，超过该天数开始衰减
        """
        decay_count = 0
        edges_to_update = []

        # 首先获取所有需要衰减的边
        for source_node_id, target_node_id, edge_data in self.graph_engine.graph.edges(data=True):
            if 'updated_at' in edge_data:
                try:
                    updated_at = datetime.fromisoformat(edge_data['updated_at'])
                    days_since_update = (datetime.now() - updated_at).days

                    if days_since_update >= days_threshold:
                        # 根据艾宾浩斯遗忘曲线衰减
                        # 衰减公式：decay = decay_rate * (days_since_update - days_threshold)
                        decay_amount = self.decay_rate * (days_since_update - days_threshold)
                        new_confidence = max(
                            self.min_confidence,
                            edge_data['confidence'] - decay_amount
                        )

                        if new_confidence < edge_data['confidence']:
                            edges_to_update.append({
                                'source_node_id': source_node_id,
                                'target_node_id': target_node_id,
                                'new_confidence': new_confidence
                            })
                            decay_count += 1
                except Exception as e:
                    print(f"处理边 {source_node_id} -> {target_node_id} 失败: {e}")

        # 使用 GraphEngine 提供的方法批量更新
        if edges_to_update:
            updated_count = self.graph_engine.decay_edges(edges_to_update)
            print(f"遗忘管理器：已衰减 {updated_count} 条边")
            return updated_count

        return 0

    def run_daily_task(self):
        """每日任务入口"""
        print(f"遗忘管理器：开始执行每日任务 at {datetime.now()}")
        self.decay_unreinforced_edges(days_threshold=7)
        print(f"遗忘管理器：每日任务完成")


def start_forgetfulness_scheduler(graph_engine, interval_hours=24):
    """启动遗忘调度器

    Args:
        graph_engine: 图谱引擎实例
        interval_hours: 执行间隔（小时）
    """
    manager = ForgetfulnessManager(graph_engine)

    def scheduler_loop():
        import time
        while True:
            try:
                manager.run_daily_task()
            except Exception as e:
                print(f"遗忘调度器出错: {e}")
            # 每小时检查一次
            time.sleep(interval_hours * 3600)

    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    print(f"遗忘调度器已启动，每 {interval_hours} 小时执行一次")
    return scheduler_thread


if __name__ == "__main__":
    search_tool = RAGSearchTool()
    result = search_tool.search_memory_api("如何使用工具")
    print(result)
