import datetime
import threading

from .core.memory_worker.worker_agent import MemoryAgent
from .core.search_tool import RAGSearchTool
from .core.utils import SingletonMeta


class PurrMemoClient(metaclass=SingletonMeta):
    def __init__(self):
        self.search_tool = RAGSearchTool()
        self._start_daemon()

    def _start_daemon(self):
        """启动守护进程监听 buffer/pending"""
        agent = MemoryAgent()
        daemon_thread = threading.Thread(target=agent.run, daemon=True)
        daemon_thread.start()
        print("✅ 后台守护进程已启动，正在监听 pending 目录...")

    def search(self, query: str = "", filters: dict = None):
        """通过混合检索匹配记忆库里的数据"""
        filters = filters or {}

        if "top_k" not in filters:
            filters["top_k"] = 5

        if "date" in filters:
            raw_date = filters.pop("date")
            if raw_date and isinstance(raw_date, str):
                try:
                    parsed_date = datetime.datetime.strptime(
                        raw_date.strip(), "%Y-%m-%d"
                    )
                    start_time = parsed_date.strftime("%Y-%m-%dT00:00:00")
                    end_time = parsed_date.strftime("%Y-%m-%dT23:59:59.999999")
                    filters["time_range"] = (start_time, end_time)
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


def get_memory_client():
    return PurrMemoClient()
