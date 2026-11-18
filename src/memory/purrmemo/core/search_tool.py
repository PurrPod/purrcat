import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from src.memory.config import (
    RAG_TOP_K_EVENTS,
    RAG_TOP_K_EXPERIENCES,
    RAG_TOP_K_GRAPH_NODES,
)
from src.memory.settings import get_memory_settings

from .clock import parse_iso
from .filters import filter_by_min_score, filter_by_time_range
from .formatting import describe_relation, format_search_results
from .schema import (
    CANDIDATE_LIMIT,
    GRAPH_NODE_SEARCH_TOP_K,
    MIN_EXPERIENCE_SCORE,
    RRF_K,
)
from .scoring import ebbinghaus_confidence, reciprocal_rank_fusion
from .storage.event_engine import EventEngine
from .storage.experience_engine import ExperienceEngine
from .storage.graph_engine import GraphEngine
from .storage.vector_engine import VectorEngine


class RAGSearchTool:
    def __init__(
        self,
        event_engine=None,
        vector_engine=None,
        graph_engine=None,
        experience_engine=None,
        max_workers=10,
    ):
        self.event_engine = event_engine if event_engine is not None else EventEngine()
        self._experience_engine = experience_engine

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

        events_results, experiences_results, graph_results = self._apply_min_score(
            events_results, experiences_results, graph_results, filters
        )
        markdown_context = self._format_results(
            events_results, experiences_results, graph_results, events_warning
        )
        return markdown_context

    def _apply_min_score(self, events, experiences, graph, filters):
        """按 filters.min_score 过滤三路结果（含边界）；未提供阈值时保持原样。"""
        raw = (filters or {}).get("min_score")
        if raw is None:
            return events, experiences, graph
        try:
            min_score = max(0.0, min(float(raw), 1.0))
        except (TypeError, ValueError):
            return events, experiences, graph
        # 经验阈值已在向量候选阶段生效，BM25-only 候选不得被丢弃（SPEC-020 4.3）
        return (
            filter_by_min_score(events, "score", min_score),
            experiences,
            filter_by_min_score(graph, "confidence", min_score),
        )

    @property
    def experience_engine(self):
        """懒加载经验库，避免只检索事件时创建数据库。"""
        if self._experience_engine is None:
            self._experience_engine = ExperienceEngine()
        return self._experience_engine

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
                vector_results_raw, bm25_results_raw, k=RRF_K, top_k=top_k
            )
            # RRF 分理论最大值为两路都排第一时的 2/(k+1)，据此归一化到 0–1 供展示
            rrf_ceiling = 2.0 / (RRF_K + 1)
            final_events = [
                {
                    **item["data"],
                    "score": min(1.0, item["rrf_score"] / rrf_ceiling),
                }
                for item in fused_results
            ]

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
        """检索经验库：向量 + BM25 融合后回 SQLite 取正文与置信度。"""
        try:
            filters = filters or {}
            if not query:
                return []

            top_k = filters.get("top_k", RAG_TOP_K_EXPERIENCES)

            vector_results = []
            if self.vector_engine:
                raw = self.vector_engine.search_experience_vectors(
                    query=query,
                    top_k=CANDIDATE_LIMIT,
                    query_embedding=query_embedding,
                )
                threshold = filters.get("min_score", MIN_EXPERIENCE_SCORE)
                try:
                    threshold = float(threshold)
                except (TypeError, ValueError):
                    threshold = MIN_EXPERIENCE_SCORE
                vector_results = [
                    {**item, "data": {}}
                    for item in raw
                    if item.get("score", 0) >= threshold
                ]

            bm25_results = [
                {**item, "data": {}}
                for item in self.experience_engine.search_bm25(
                    query, limit=CANDIDATE_LIMIT
                )
            ]

            fused = reciprocal_rank_fusion(
                vector_results, bm25_results, k=RRF_K, top_k=top_k
            )
            # SQLite 不存在的 id 直接丢弃，避免向量删除延迟暴露已删数据
            return self.experience_engine.get_many([item["id"] for item in fused])
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

    def decay_unreinforced_edges(self, days_threshold=1, since=None, now=None):
        """按艾宾浩斯曲线衰减长时间未强化的边（SPEC-020 AC-10）。

        ``since`` 为上次遗忘任务的时间；边的实际衰减区间从
        ``max(边 updated_at, since)`` 起算，避免重复衰减。
        """
        half_life_days = get_memory_settings()["decay_half_life_days"]
        current = now or datetime.now()
        since_time = None
        if since:
            try:
                since_time = parse_iso(since)
            except (TypeError, ValueError):
                since_time = None

        edges_to_update = []

        for source_node_id, target_node_id, edge_data in self.graph_engine.graph.edges(
            data=True
        ):
            if "updated_at" not in edge_data:
                continue
            try:
                anchor = parse_iso(edge_data["updated_at"])
                if since_time and since_time > anchor:
                    anchor = since_time
                elapsed_days = max(0.0, (current - anchor).total_seconds() / 86400)

                if elapsed_days < days_threshold:
                    continue
                new_confidence = ebbinghaus_confidence(
                    edge_data["confidence"],
                    elapsed_days,
                    floor=self.min_confidence,
                    half_life_days=half_life_days,
                )

                if new_confidence < edge_data["confidence"]:
                    edges_to_update.append(
                        {
                            "source_node_id": source_node_id,
                            "target_node_id": target_node_id,
                            "new_confidence": new_confidence,
                        }
                    )
            except (TypeError, ValueError) as e:
                print(f"处理边 {source_node_id} -> {target_node_id} 失败: {e}")

        if edges_to_update:
            return self.graph_engine.decay_edges(edges_to_update)

        return 0

    def run_daily_task(self):
        """每日任务入口；距上次成功衰减不足 24 小时则跳过。"""
        from src.memory.settings import read_memory_state, update_memory_state

        current = datetime.now()
        last_run_at = read_memory_state().get("last_decay_at")
        if last_run_at:
            try:
                elapsed = (current - parse_iso(last_run_at)).total_seconds()
            except (TypeError, ValueError):
                elapsed = None
            if elapsed is not None and 0 <= elapsed < 24 * 3600:
                return

        self.decay_unreinforced_edges(
            days_threshold=1, since=last_run_at, now=current
        )
        update_memory_state({"last_decay_at": current.isoformat()})

        retention_days = get_memory_settings()["event_retention_days"]
        if retention_days <= 0:
            return  # 0 = 永久保留

        try:
            event_engine = (
                self.event_engine if self.event_engine is not None else EventEngine()
            )
            deleted_count = event_engine.cleanup_old_events(
                days_threshold=retention_days
            )
            if deleted_count > 0:
                print(
                    f"🧹 [遗忘机制] 已清理 {deleted_count} 条超过{retention_days}天的陈旧事件"
                )
        except Exception as e:
            print(f"执行事件清理任务失败: {e}")


def start_forgetfulness_scheduler(graph_engine):
    """启动遗忘调度器。

    是否到期待执行由 ``run_daily_task`` 依据 ``memory.json`` 里的
    ``last_decay_at`` 判断；这里只负责定期唤醒，避免重启后顺延一天。
    """
    manager = ForgetfulnessManager(graph_engine)

    def scheduler_loop():
        import time

        while True:
            try:
                manager.run_daily_task()
            except Exception as e:
                print(f"遗忘调度器出错: {e}")
            time.sleep(3600)

    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    return scheduler_thread


if __name__ == "__main__":
    search_tool = RAGSearchTool()
    result = search_tool.search_memory_api("如何使用工具")
    print(result)
