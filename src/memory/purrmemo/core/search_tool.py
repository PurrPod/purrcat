import os
import json
from datetime import datetime, timedelta
import threading
import numpy as np
from .config import RAG_CONFIG
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

    for rank, item in enumerate(sorted(vector_results, key=lambda x: x['score'], reverse=True)):
        item_id = item['id']
        fused_scores[item_id] = fused_scores.get(item_id, 0) + 1.0 / (k + rank + 1)
        fused_data[item_id] = item['data']

    for rank, item in enumerate(sorted(bm25_results, key=lambda x: x['score'], reverse=True)):
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

    def search_memory_api(self, query: str, filters: dict = None):
        """统一检索接口

        Args:
            query: 查询文本
            filters: 过滤条件（可选）

        Returns:
            结构化的 Markdown 上下文
        """
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
        """检索事件库 - 混合检索版（向量 + BM25 + RRF融合）

        Returns:
            dict: {"events": [...], "warning": "..."}
            warning 为空表示无降级查询，有内容表示使用了降级查询并说明原因
        """
        filters = filters or {}
        try:
            top_k = filters.get('top_k', RAG_CONFIG['top_k_events'])
            start_time, end_time = filters.get('time_range', (None, None))
            had_time_filter = start_time is not None and end_time is not None

            if not query:
                if had_time_filter:
                    events = self.event_engine.get_events_by_time_range(start_time, end_time, limit=top_k)
                else:
                    events = self.event_engine.get_latest_events(limit=top_k)
                return {"events": events, "warning": ""}

            vector_results_raw = []
            pool = None
            if self.vector_engine:
                query_vector = self.vector_engine._get_embedding(query)

                if start_time:
                    pool = self.event_engine.get_events_by_time_range(start_time, end_time, limit=200)
                else:
                    pool = self.event_engine.get_latest_events(limit=200)

                if pool:
                    valid_events = [e for e in pool if e.get('vector')]

                    if valid_events:
                        vectors_matrix = np.array([e['vector'] for e in valid_events])
                        dot_products = np.dot(vectors_matrix, query_vector)
                        query_norm = np.linalg.norm(query_vector)
                        matrix_norms = np.linalg.norm(vectors_matrix, axis=1)
                        similarities = dot_products / (matrix_norms * query_norm + 1e-9)

                        for idx, e in enumerate(valid_events):
                            vector_results_raw.append({"id": e['event_id'], "data": e, "score": similarities[idx]})

            bm25_results_raw = self.event_engine.search_fts_bm25(query, start_time, end_time, limit=200)

            fused_results = reciprocal_rank_fusion(vector_results_raw, bm25_results_raw, top_k=top_k)

            final_events = [item['data'] for item in fused_results]

            fallback_warning = ""
            if not final_events and had_time_filter:
                fallback_warning = f"⚠️ 当前筛选日期内未找到与检索相关的事件。\n\n"
                final_events = []
            elif not final_events:
                final_events = []

            return {"events": final_events, "warning": fallback_warning}
        except Exception as e:
            print(f"检索事件失败: {e}")
            return {"events": [], "warning": ""}

    def _search_experiences(self, query: str, filters: dict = None):
        """检索经验库"""
        try:
            if not self.vector_engine:
                return []

            raw_experiences = self.vector_engine.search_experiences(
                query=query,
                top_k=RAG_CONFIG['top_k_experiences'],
                filters=filters
            )

            valid_experiences = []
            for exp in raw_experiences:
                similarity = 1.0 - exp['score']
                if similarity >= 0.35:
                    valid_experiences.append(exp)

            return valid_experiences
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
            seen_edges = set()

            if hasattr(self.graph_engine, 'vector_engine') and self.graph_engine.vector_engine:
                similar_nodes = self.graph_engine.vector_engine.search_graph_nodes(query, top_k=5)
            else:
                return []

            for node_info in similar_nodes:
                node_id = node_info['node_id']
                relations = self.graph_engine.get_relations_by_node(node_id, direction='all')
                for relation in relations:
                    edge_id = relation.get('edge_id')

                    if edge_id in seen_edges:
                        continue
                    if edge_id:
                        seen_edges.add(edge_id)

                    if relation['confidence'] >= self.graph_engine.min_confidence:
                        target_node = self.graph_engine.get_node(relation['target_node_id'])
                        target_name = target_node['name'] if target_node else '未知'

                        source_node = self.graph_engine.get_node(relation['source_node_id'])
                        source_name = source_node['name'] if source_node else '未知'

                        relation_desc = f"{source_name} {relation['relation_meaning']} {target_name}"
                        results.append({
                            'source': source_name,
                            'relation': relation['relation_meaning'],
                            'target': target_name,
                            'confidence': relation['confidence'],
                            'description': relation_desc
                        })

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

        for source_node_id, target_node_id, edge_data in self.graph_engine.graph.edges(data=True):
            if 'updated_at' in edge_data:
                try:
                    updated_at = datetime.fromisoformat(edge_data['updated_at'])
                    days_since_update = (datetime.now() - updated_at).days

                    if days_since_update >= days_threshold:
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

        if edges_to_update:
            updated_count = self.graph_engine.decay_edges(edges_to_update)
            return updated_count

        return 0

    def run_daily_task(self):
        """每日任务入口"""
        self.decay_unreinforced_edges(days_threshold=7)


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
            time.sleep(interval_hours * 3600)

    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    return scheduler_thread


if __name__ == "__main__":
    search_tool = RAGSearchTool()
    result = search_tool.search_memory_api("如何使用工具")
    print(result)
