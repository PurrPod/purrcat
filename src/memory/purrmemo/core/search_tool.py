from datetime import datetime
import threading
from src.utils.config import get_memory_config
from .storage.event_engine import EventEngine
from .storage.vector_engine import VectorEngine
from .storage.graph_engine import GraphEngine
from concurrent.futures import ThreadPoolExecutor, as_completed


def reciprocal_rank_fusion(vector_results, bm25_results, k=60, top_k=5):
    """
    RRF 倒数排名融合算法
    :param vector_results: 列表，包含 {'id': 'xxx', 'data': {...}, 'score': 0.8}
    :param bm25_results: 列表，包含 {'id': 'xxx', 'data': {...}, 'score': 15.2}
    """
    fused_scores = {}
    fused_data = {}

    # 将两个列表放在一起遍历，消除重复代码块
    for result_list in (vector_results, bm25_results):
        for rank, item in enumerate(sorted(result_list, key=lambda x: x['score'], reverse=True)):
            item_id = item['id']
            fused_scores[item_id] = fused_scores.get(item_id, 0) + 1.0 / (k + rank + 1)
            fused_data[item_id] = item['data']

    reranked = [
        {"id": item_id, "data": fused_data[item_id], "rrf_score": score}
        for item_id, score in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    ]

    return reranked[:top_k]

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

        self.executor = ThreadPoolExecutor(max_workers=10)

    def search_memory_api(self, query: str, filters: dict = None):
        """统一检索接口"""
        events_results = []
        experiences_results = []
        graph_results = []

        # 统一向量化，避免并发死锁
        query_embedding = None
        if self.vector_engine and query:
            try:
                query_embedding = self.vector_engine._get_embedding(query)
            except Exception as e:
                print(f"❌ [RAGSearchTool] Embedding 计算失败: {e}")

        # 使用全局线程池提交任务
        future_to_source = {
            self.executor.submit(self._search_events, query, filters, query_embedding): 'events',
            self.executor.submit(self._search_experiences, query, filters, query_embedding): 'experiences',
            self.executor.submit(self._search_graph, query, filters, query_embedding): 'graph'
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
                print(f"❌ [RAGSearchTool] 检索 {source} 失败: {e}")

        markdown_context = self._format_results(events_results, experiences_results, graph_results, events_warning)
        return markdown_context

    def _search_events(self, query: str, filters: dict = None, query_embedding=None):
        """检索事件库 - 混合检索版"""
        filters = filters or {}
        rag_config = get_memory_config().get('rag', {})
        try:
            top_k = filters.get('top_k', rag_config.get('top_k_events', 5))
            start_time, end_time = filters.get('time_range', (None, None))

            if not query:
                # 使用合并后的 get_events 方法
                events = self.event_engine.get_events(start_time, end_time, limit=top_k)
                return {"events": events, "warning": ""}

            vector_results_raw = []
            if self.vector_engine:
                vector_results_raw = self.vector_engine.search_events_vector(
                    query, top_k=200, query_embedding=query_embedding
                )
                
                if start_time and end_time:
                    vector_results_raw = [
                        e for e in vector_results_raw 
                        if start_time <= e['data']['timestamp'] <= end_time
                    ]

            bm25_results_raw = self.event_engine.search_fts_bm25(query, start_time, end_time, limit=200)

            fused_results = reciprocal_rank_fusion(vector_results_raw, bm25_results_raw, top_k=top_k)
            final_events = [item['data'] for item in fused_results]

            fallback_warning = ""
            if not final_events and start_time and end_time:
                fallback_warning = "⚠️ 当前筛选日期内未找到与检索相关的事件。\n\n"

            return {"events": final_events, "warning": fallback_warning}
        except Exception as e:
            print(f"检索事件失败: {e}")
            return {"events": [], "warning": ""}

    def _search_experiences(self, query: str, filters: dict = None, query_embedding=None):
        """检索经验库"""
        rag_config = get_memory_config().get('rag', {})
        try:
            if not self.vector_engine:
                return []

            top_k = filters.get('top_k', rag_config.get('top_k_experiences', 5)) if filters else rag_config.get('top_k_experiences', 5)
            raw_experiences = self.vector_engine.search_experiences(
                query=query,
                top_k=top_k,
                filters=filters,
                query_embedding=query_embedding
            )

            return [exp for exp in raw_experiences if 1.0 - exp['score'] >= 0.35]
        except Exception as e:
            print(f"检索经验失败: {e}")
            return []

    def _search_graph(self, query: str, filters: dict = None, query_embedding=None):
        """检索图谱库"""
        rag_config = get_memory_config().get('rag', {})
        try:
            if not self.graph_engine:
                return []

            if self.graph_engine.get_graph_stats()['nodes'] == 0:
                return []

            results = []
            seen_edges = set()

            if hasattr(self.graph_engine, 'vector_engine') and self.graph_engine.vector_engine:
                similar_nodes = self.graph_engine.vector_engine.search_graph_nodes(
                    query, top_k=5, query_embedding=query_embedding
                )
            else:
                return []

            for node_info in similar_nodes:
                relations = self.graph_engine.get_relations_by_node(node_info['node_id'], direction='all')
                for relation in relations:
                    edge_id = relation.get('edge_id')
                    if edge_id and edge_id in seen_edges:
                        continue
                    if edge_id:
                        seen_edges.add(edge_id)

                    if relation['confidence'] >= self.graph_engine.min_confidence:
                        target_node = self.graph_engine.get_node(relation['target_node_id'])
                        source_node = self.graph_engine.get_node(relation['source_node_id'])
                        
                        results.append({
                            'source': source_node['name'] if source_node else '未知',
                            'relation': relation['relation_meaning'],
                            'target': target_node['name'] if target_node else '未知',
                            'confidence': relation['confidence'],
                            'description': f"{source_node['name'] if source_node else '未知'} {relation['relation_meaning']} {target_node['name'] if target_node else '未知'}"
                        })

            results.sort(key=lambda x: x['confidence'], reverse=True)
            top_k = filters.get('top_k', rag_config.get('top_k_graph_nodes', 3)) if filters else rag_config.get('top_k_graph_nodes', 3)
            return results[:top_k]
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
            markdown_parts.extend([f"- [{event['timestamp']}] {event['content']}" for event in events])
            markdown_parts.append("")

        if experiences:
            markdown_parts.append("## 工作经验")
            markdown_parts.extend([f"- [{1.0 - exp['score']:.2f}] {exp['content']}" for exp in experiences])
            markdown_parts.append("")

        if graph_results:
            markdown_parts.append("## 知识图谱")
            markdown_parts.extend([f"- {result['description']} (置信度: {result['confidence']:.2f})" for result in graph_results])
            markdown_parts.append("")

        if not markdown_parts:
            markdown_parts.append("## 检索结果")
            markdown_parts.append("没有找到相关信息")

        return "\n".join(markdown_parts)


class ForgetfulnessManager:
    """遗忘管理器"""

    def __init__(self, graph_engine, min_confidence=0.3, decay_rate=0.05):
        self.graph_engine = graph_engine
        self.min_confidence = min_confidence
        self.decay_rate = decay_rate

    def decay_unreinforced_edges(self, days_threshold=7):
        """衰减长时间未强化的边"""
        edges_to_update = []

        for source_node_id, target_node_id, edge_data in self.graph_engine.graph.edges(data=True):
            if 'updated_at' in edge_data:
                try:
                    updated_at = datetime.fromisoformat(edge_data['updated_at'])
                    days_since_update = (datetime.now() - updated_at).days

                    if days_since_update >= days_threshold:
                        decay_amount = self.decay_rate * (days_since_update - days_threshold)
                        new_confidence = max(self.min_confidence, edge_data['confidence'] - decay_amount)

                        if new_confidence < edge_data['confidence']:
                            edges_to_update.append({
                                'source_node_id': source_node_id,
                                'target_node_id': target_node_id,
                                'new_confidence': new_confidence
                            })
                except Exception as e:
                    print(f"处理边 {source_node_id} -> {target_node_id} 失败: {e}")

        if edges_to_update:
            return self.graph_engine.decay_edges(edges_to_update)

        return 0

    def run_daily_task(self):
        """每日任务入口"""
        self.decay_unreinforced_edges(days_threshold=7)
        
        try:
            event_engine = EventEngine()
            deleted_count = event_engine.cleanup_old_events(days_threshold=90)
            if deleted_count > 0:
                print(f"🧹 [遗忘机制] 已清理 {deleted_count} 条超过90天的陈旧事件")
        except Exception as e:
            print(f"执行事件清理任务失败: {e}")


def start_forgetfulness_scheduler(graph_engine, interval_hours=24):
    """启动遗忘调度器"""
    manager = ForgetfulnessManager(graph_engine)

    def scheduler_loop():
        import time
        while True:
            try:
                manager.run_daily_task()
            except Exception as e:
                print(f"遗忘调度器出错: {e}")
            time.sleep(interval_hours * 3600)

    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    return scheduler_thread


if __name__ == "__main__":
    search_tool = RAGSearchTool()
    result = search_tool.search_memory_api("如何使用工具")
    print(result)
