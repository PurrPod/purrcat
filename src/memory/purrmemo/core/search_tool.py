import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.memory.config import (
    RAG_TOP_K_EVENTS,
    RAG_TOP_K_EXPERIENCES,
    RAG_TOP_K_GRAPH_NODES,
)

from .clock import days_since
from .filters import filter_by_time_range, filter_experiences_by_score
from .formatting import describe_relation, format_search_results
from .schema import CANDIDATE_LIMIT, GRAPH_NODE_SEARCH_TOP_K, MIN_EXPERIENCE_SCORE
from .scoring import decayed_confidence, reciprocal_rank_fusion
from .storage.event_engine import EventEngine
from .storage.graph_engine import GraphEngine
from .storage.vector_engine import VectorEngine


class RAGSearchTool:
    def __init__(
        self, event_engine=None, vector_engine=None, graph_engine=None, max_workers=10
    ):
        self.event_engine = event_engine if event_engine is not None else EventEngine()

        if vector_engine is not None:
            self.vector_engine = vector_engine
        else:
            self.vector_engine = None
            try:
                self.vector_engine = VectorEngine()
            except Exception:
                print("VectorEngine 不可用，将无法检索经验库")

        if graph_engine is not None:
            self.graph_engine = graph_engine
        else:
            self.graph_engine = None
            try:
                self.graph_engine = GraphEngine()
            except Exception:
                print("GraphEngine 不可用，将无法检索图谱库")

        self.executor = ThreadPoolExecutor(max_workers=max_workers)

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
            self.executor.submit(
                self._search_events, query, filters, query_embedding
            ): "events",
            self.executor.submit(
                self._search_experiences, query, filters, query_embedding
            ): "experiences",
            self.executor.submit(
                self._search_graph, query, filters, query_embedding
            ): "graph",
        }

        events_warning = ""
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                result = future.result()
                if source == "events":
                    if isinstance(result, dict):
                        events_warning = result.get("warning", "")
                        events_results = result.get("events", [])
                    else:
                        events_results = result
                elif source == "experiences":
                    experiences_results = result
                elif source == "graph":
                    graph_results = result
            except Exception as e:
                print(f"❌ [RAGSearchTool] 检索 {source} 失败: {e}")

        markdown_context = self._format_results(
            events_results, experiences_results, graph_results, events_warning
        )
        return markdown_context

    def _search_events(self, query: str, filters: dict = None, query_embedding=None):
        """检索事件库 - 混合检索版"""
        filters = filters or {}
        try:
            top_k = filters.get("top_k", RAG_TOP_K_EVENTS)
            start_time, end_time = filters.get("time_range", (None, None))

            if not query:
                # 使用合并后的 get_events 方法
                events = self.event_engine.get_events(start_time, end_time, limit=top_k)
                return {"events": events, "warning": ""}

            vector_results_raw = []
            if self.vector_engine:
                vector_results_raw = self.vector_engine.search_events_vector(
                    query, top_k=CANDIDATE_LIMIT, query_embedding=query_embedding
                )

                if start_time and end_time:
                    vector_results_raw = filter_by_time_range(
                        vector_results_raw, start_time, end_time
                    )

            bm25_results_raw = self.event_engine.search_fts_bm25(
                query, start_time, end_time, limit=CANDIDATE_LIMIT
            )

            fused_results = reciprocal_rank_fusion(
                vector_results_raw, bm25_results_raw, top_k=top_k
            )
            final_events = [item["data"] for item in fused_results]

            fallback_warning = ""
            if not final_events and start_time and end_time:
                fallback_warning = "⚠️ 当前筛选日期内未找到与检索相关的事件。\n\n"

            return {"events": final_events, "warning": fallback_warning}
        except Exception as e:
            print(f"检索事件失败: {e}")
            return {"events": [], "warning": ""}

    def _search_experiences(
        self, query: str, filters: dict = None, query_embedding=None
    ):
        """检索经验库"""
        try:
            if not self.vector_engine:
                return []

            top_k = (
                filters.get("top_k", RAG_TOP_K_EXPERIENCES)
                if filters
                else RAG_TOP_K_EXPERIENCES
            )
            raw_experiences = self.vector_engine.search_experiences(
                query=query,
                top_k=top_k,
                filters=filters,
                query_embedding=query_embedding,
            )

            return filter_experiences_by_score(raw_experiences, MIN_EXPERIENCE_SCORE)
        except Exception as e:
            print(f"检索经验失败: {e}")
            return []

    def _search_graph(self, query: str, filters: dict = None, query_embedding=None):
        """检索图谱库"""
        try:
            if not self.graph_engine:
                return []

            if self.graph_engine.get_graph_stats()["nodes"] == 0:
                return []

            results = []
            seen_edges = set()

            if (
                hasattr(self.graph_engine, "vector_engine")
                and self.graph_engine.vector_engine
            ):
                similar_nodes = self.graph_engine.vector_engine.search_graph_nodes(
                    query,
                    top_k=GRAPH_NODE_SEARCH_TOP_K,
                    query_embedding=query_embedding,
                )
            else:
                return []

            for node_info in similar_nodes:
                relations = self.graph_engine.get_relations_by_node(
                    node_info["node_id"], direction="all"
                )
                for relation in relations:
                    edge_id = relation.get("edge_id")
                    if edge_id and edge_id in seen_edges:
                        continue
                    if edge_id:
                        seen_edges.add(edge_id)

                    if relation["confidence"] >= self.graph_engine.min_confidence:
                        target_node = self.graph_engine.get_node(
                            relation["target_node_id"]
                        )
                        source_node = self.graph_engine.get_node(
                            relation["source_node_id"]
                        )

                        source_name = source_node["name"] if source_node else "未知"
                        target_name = target_node["name"] if target_node else "未知"

                        results.append(
                            {
                                "source": source_name,
                                "relation": relation["relation_meaning"],
                                "target": target_name,
                                "confidence": relation["confidence"],
                                "description": describe_relation(
                                    source_name,
                                    relation["relation_meaning"],
                                    target_name,
                                ),
                            }
                        )

            results.sort(key=lambda x: x["confidence"], reverse=True)
            top_k = (
                filters.get("top_k", RAG_TOP_K_GRAPH_NODES)
                if filters
                else RAG_TOP_K_GRAPH_NODES
            )
            return results[:top_k]
        except Exception as e:
            print(f"检索图谱失败: {e}")
            return []

    def _format_results(self, events, experiences, graph_results, events_warning=""):
        """将结果格式化为 Markdown"""
        return format_search_results(events, experiences, graph_results, events_warning)


class ForgetfulnessManager:
    """遗忘管理器"""

    def __init__(
        self, graph_engine, min_confidence=0.3, decay_rate=0.05, event_engine=None
    ):
        self.graph_engine = graph_engine
        self.min_confidence = min_confidence
        self.decay_rate = decay_rate
        self.event_engine = event_engine

    def decay_unreinforced_edges(self, days_threshold=7):
        """衰减长时间未强化的边"""
        edges_to_update = []

        for source_node_id, target_node_id, edge_data in self.graph_engine.graph.edges(
            data=True
        ):
            if "updated_at" in edge_data:
                try:
                    days_since_update = days_since(edge_data["updated_at"])
                    new_confidence = decayed_confidence(
                        edge_data["confidence"],
                        days_since_update,
                        days_threshold,
                        self.decay_rate,
                        self.min_confidence,
                    )

                    if new_confidence is not None:
                        edges_to_update.append(
                            {
                                "source_node_id": source_node_id,
                                "target_node_id": target_node_id,
                                "new_confidence": new_confidence,
                            }
                        )
                except Exception as e:
                    print(f"处理边 {source_node_id} -> {target_node_id} 失败: {e}")

        if edges_to_update:
            return self.graph_engine.decay_edges(edges_to_update)

        return 0

    def run_daily_task(self):
        """每日任务入口"""
        self.decay_unreinforced_edges(days_threshold=7)

        try:
            event_engine = (
                self.event_engine if self.event_engine is not None else EventEngine()
            )
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
