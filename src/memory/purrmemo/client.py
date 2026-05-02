import threading
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

    def search(self, query: str, filter_date: str = None, topk: int = 5):
        """
        通过 RAG 匹配记忆库里的数据

        :param query: 搜索语句
        :param filter_date: 日期限制，格式需为 "YYYY-MM-DD"
        :param topk: 返回个数，按评分优先
        :return: Markdown 格式的检索结果
        """
        RAG_CONFIG['top_k_events'] = topk
        RAG_CONFIG['top_k_experiences'] = topk
        RAG_CONFIG['top_k_graph_nodes'] = topk

        filters = {}
        if filter_date:
            start_time = f"{filter_date}T00:00:00"
            end_time = f"{filter_date}T23:59:59.999999"
            filters['time_range'] = (start_time, end_time)

        return self.search_tool.search_memory_api(query=query, filters=filters)


def get_memory_client():
    """获取全局记忆客户端单例"""
    return PurrMemoClient()
