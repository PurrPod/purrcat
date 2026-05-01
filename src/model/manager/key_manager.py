import threading


class APIKeyManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._usage = {}
                cls._instance._usage_lock = threading.Lock()
        return cls._instance

    def allocate_key(self, valid_keys: list, recovered_key_prefix: str = None) -> str:
        """分配最空闲的 API Key，支持根据前缀恢复"""
        if not valid_keys:
            raise ValueError("没有提供有效的 API Key 列表")

        with self._usage_lock:
            if recovered_key_prefix:
                matched_key = next((k for k in valid_keys if k.startswith(recovered_key_prefix)), None)
                if matched_key:
                    self._usage[matched_key] = self._usage.get(matched_key, 0) + 1
                    return matched_key

            best_key = min(valid_keys, key=lambda k: self._usage.get(k, 0))
            self._usage[best_key] = self._usage.get(best_key, 0) + 1
            return best_key

    def release_key(self, api_key: str):
        """释放 API Key 的活跃状态"""
        if not api_key:
            return

        with self._usage_lock:
            if api_key in self._usage:
                self._usage[api_key] = max(0, self._usage[api_key] - 1)

    def get_active_count(self, api_key: str) -> int:
        """获取某个 Key 的当前活跃数"""
        with self._usage_lock:
            return self._usage.get(api_key, 0)


key_manager = APIKeyManager()