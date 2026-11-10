import os
import json
import time
import threading
import atexit

from src.model.manager.usage_stats import (
    apply_delta,
    empty_bucket,
    extract_usage_fields,
    mask_api_key,
    merge_into_disk,
    today_str,
)
from src.utils.config import TRACKER_DIR


class ModelUsageTracer:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self.base_dir = os.path.join(TRACKER_DIR, "model_usage")
        os.makedirs(self.base_dir, exist_ok=True)

        self._data_lock = threading.Lock()

        # 内存中暂存的增量数据 (Delta)
        # 格式：{ "2026-06-10": { "model_name|masked_key": { "calls": 0, "total_tokens": 0 ...} } }
        self._pending_deltas = {}

        self._last_flush = time.time()
        self._flush_interval = 60.0  # 每隔 60 秒刷一次盘（可调）

        # 注册退出钩子，确保进程被杀死或结束时最后刷一次盘
        atexit.register(self.flush)

    def _mask_api_key(self, api_key: str) -> str:
        return mask_api_key(api_key)

    def record(self, model_name: str, api_key: str, usage, duration: float):
        """完全对齐 OpenAI SDK v1.x，并深度提取缓存与思考 Token"""
        if not usage:
            return

        date_str = today_str()
        masked_key = self._mask_api_key(api_key)
        hash_key = f"{model_name}|{masked_key}"
        fields = extract_usage_fields(usage)

        with self._data_lock:
            day = self._pending_deltas.setdefault(date_str, {})
            bucket = day.get(hash_key)
            if bucket is None:
                bucket = day[hash_key] = empty_bucket(model_name, masked_key)
            apply_delta(bucket, fields, duration)

            if time.time() - self._last_flush > self._flush_interval:
                self._flush_unlocked()

    def flush(self):
        """提供给外部手动刷盘的接口（或 atexit 自动调用）"""
        with self._data_lock:
            self._flush_unlocked()

    def _flush_unlocked(self):
        """真正的硬盘 I/O：读取硬盘旧数据 -> 加上内存增量 -> 覆盖写入"""
        if not self._pending_deltas:
            return

        for date_str, items in self._pending_deltas.items():
            file_path = os.path.join(self.base_dir, f"{date_str}_summary.json")

            # 1. 读出硬盘现有的总计数据
            disk_data = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        disk_data = json.load(f)
                except Exception:
                    pass

            # 2. 将内存增量累加进去
            merged = merge_into_disk(disk_data, items)

            # 3. 写回磁盘 (格式化保存)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

        # 4. 账本清零，重新开始下一轮记账
        self._pending_deltas.clear()
        self._last_flush = time.time()


# 暴露单例
usage_tracer = ModelUsageTracer()
