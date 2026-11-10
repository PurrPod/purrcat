import threading
import traceback

from .core.filters import date_range_for
from .core.formatting import collection_records_to_experiences, graph_to_payload
from .core.memory_worker.worker_agent import MemoryAgent
from .core.schema import DEFAULT_SEARCH_TOP_K
from .core.search_tool import RAGSearchTool
from .core.utils import SingletonMeta
from .visualize_graph import GraphVisualizer
from src.utils.memory_utils import validate_memo_data, write_to_pending


class PurrMemoClient(metaclass=SingletonMeta):
    def __init__(self, search_tool=None, auto_start=True):
        self.search_tool = search_tool if search_tool is not None else RAGSearchTool()
        self._daemon_started = False
        if auto_start:
            self.init()

    def _start_daemon(self):
        """启动守护进程监听 buffer/pending"""
        agent = MemoryAgent()
        daemon_thread = threading.Thread(target=agent.run, daemon=True)
        daemon_thread.start()
        self._daemon_started = True
        print("✅ 后台守护进程已启动，正在监听 pending 目录...")

    def init(self):
        """初始化 Memory Client，启动后台守护进程。

        该方法是幂等的，重复调用不会重复启动守护线程。
        """
        if not self._daemon_started:
            self._start_daemon()
        return True

    def search(self, query: str = "", filters: dict = None):
        """通过混合检索匹配记忆库里的数据"""
        filters = filters or {}

        if "top_k" not in filters:
            filters["top_k"] = DEFAULT_SEARCH_TOP_K

        if "date" in filters:
            raw_date = filters.pop("date")
            if raw_date and isinstance(raw_date, str):
                try:
                    filters["time_range"] = date_range_for(raw_date)
                except ValueError:
                    print(
                        f"⚠️ [PurrMemo] 忽略无效的日期过滤参数 '{raw_date}'，期望格式为 YYYY-MM-DD"
                    )

        print(
            f"🔍 [PurrMemo] search_tool.search_memory_api | query={query!r} | filters={filters}"
        )
        result = self.search_tool.search_memory_api(query=query, filters=filters)
        print(
            f"🔍 [PurrMemo] search_memory_api 返回 | result长度={len(result) if result else 0}"
        )
        return result

    def add_memory(self, memo_data: dict) -> str:
        """写入待处理记忆，返回 pending 文件路径。"""
        valid_data, errors = validate_memo_data(memo_data)
        if errors:
            raise ValueError("; ".join(errors))

        filepath = write_to_pending(
            events=valid_data["events"],
            cognition=valid_data["cognition"],
            user_profile=valid_data["user_profile"],
            work_exp=valid_data["work_exp"],
            source="memory_api",
        )
        return filepath

    def get_graph(self) -> dict:
        """获取图谱节点与边的简单表示。"""
        graph_engine = self.search_tool.graph_engine
        if not graph_engine or not getattr(graph_engine, "graph", None):
            return {"nodes": [], "edges": []}

        graph = graph_engine.graph
        return graph_to_payload(graph)

    def get_recent_events(self, limit: int = 30):
        """获取最近的事件（从事件库）"""
        try:
            return self.search_tool.event_engine.get_events(limit=limit)
        except Exception:
            return []

    def get_recent_experiences(self, limit: int = 30):
        """获取最近的经验（从向量库）"""
        try:
            vector_engine = self.search_tool.vector_engine
            if not vector_engine or not getattr(vector_engine, "collection", None):
                return []
            results = vector_engine.collection.get(include=["documents", "metadatas"])
            return collection_records_to_experiences(results, limit)
        except Exception as e:
            print(f"[PurrMemo] 获取最近经验失败（工作经验库将为空）: {e}")
            traceback.print_exc()
            return []

    def visualize_graph(self, output_file=None):
        """生成图谱可视化 HTML 文件"""
        try:
            visualizer = GraphVisualizer()
            visualizer.visualize(output_file=output_file)
            return True
        except Exception as e:
            print(f"可视化失败: {e}")
            return False


def get_memory_client():
    return PurrMemoClient()
