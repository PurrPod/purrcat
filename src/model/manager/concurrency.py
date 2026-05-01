import threading
from collections import defaultdict


class ConcurrencyController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._semaphores = {}
                cls._instance._semaphores_lock = threading.Lock()
                cls._instance._default_limit = 1
        return cls._instance

    def get_semaphore(self, api_key: str, limit: int = None) -> threading.Semaphore:
        """获取或创建指定 API Key 的信号量"""
        effective_limit = limit or self._default_limit

        with self._semaphores_lock:
            if api_key not in self._semaphores:
                self._semaphores[api_key] = threading.Semaphore(effective_limit)
            return self._semaphores[api_key]

    def set_default_limit(self, limit: int):
        """设置默认的并发限制"""
        self._default_limit = limit


_controller = ConcurrencyController()


def get_key_semaphore(api_key: str, max_concurrency: int = 1) -> threading.Semaphore:
    """便捷函数：获取指定 API Key 的信号量"""
    return _controller.get_semaphore(api_key, max_concurrency)