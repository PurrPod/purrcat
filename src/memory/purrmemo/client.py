import threading
import datetime
from .core.config import MEMORY_AGENT_CONFIG, RAG_CONFIG
from .core.memory_worker.worker_agent import MemoryAgent
from .core.search_tool import RAGSearchTool


class PurrMemoClient:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PurrMemoClient, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.search_tool = RAGSearchTool()
        self._start_daemon()
        self._initialized = True

    def _start_daemon(self):
        """启动守护进程监听 buffer/pending"""
        agent = MemoryAgent()
        daemon_thread = threading.Thread(target=agent.run, daemon=True)
        daemon_thread.start()
        print("✅ 后台守护进程已启动，正在监听 pending 目录...")

    def search(self, query: str = "", filters: dict = None):
        """
        通过混合检索匹配记忆库里的数据

        :param query: 搜索语句
        :param filters: 过滤条件字典，支持 top_k, date, latest_n 等
        :return: Markdown 格式的检索结果
        """
        filters = filters or {}

        top_k = filters.get('top_k', 5)
        RAG_CONFIG['top_k_events'] = top_k
        RAG_CONFIG['top_k_experiences'] = top_k
        RAG_CONFIG['top_k_graph_nodes'] = top_k

        if 'date' in filters:
            raw_date = filters.pop('date')
            if raw_date and isinstance(raw_date, str):
                try:
                    parsed_date = datetime.datetime.strptime(raw_date.strip(), "%Y-%m-%d")
                    start_time = parsed_date.strftime("%Y-%m-%dT00:00:00")
                    end_time = parsed_date.strftime("%Y-%m-%dT23:59:59.999999")
                    filters['time_range'] = (start_time, end_time)
                except ValueError:
                    print(f"⚠️ [PurrMemo] 忽略无效的日期过滤参数 '{raw_date}'，期望格式为 YYYY-MM-DD")

        return self.search_tool.search_memory_api(query=query, filters=filters)


def get_memory_client():
    """获取全局记忆客户端单例"""
    return PurrMemoClient()
