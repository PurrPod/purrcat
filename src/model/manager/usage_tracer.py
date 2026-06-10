import os
import json
import time
import threading
import atexit
from datetime import datetime
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
        if not api_key:
            return "UNKNOWN"
        if len(api_key) <= 10:
            return "***"
        return f"{api_key[:6]}***{api_key[-4:]}"

    def record(self, model_name: str, api_key: str, usage, duration: float):
        """完全对齐 OpenAI SDK v1.x，并深度提取缓存与思考 Token"""
        if not usage:
            return

        date_str = datetime.now().strftime("%Y-%m-%d")
        masked_key = self._mask_api_key(api_key)
        hash_key = f"{model_name}|{masked_key}"

        # 1. 提取标准基础字段
        p_tokens = getattr(usage, "prompt_tokens", 0)
        c_tokens = getattr(usage, "completion_tokens", 0)
        t_tokens = getattr(usage, "total_tokens", 0)

        # 2. 提取高级字段：上下文缓存命中 (折扣区)
        cached_tokens = 0
        p_details = getattr(usage, "prompt_tokens_details", None)
        if p_details:
            cached_tokens = getattr(p_details, "cached_tokens", 0)

        # 3. 提取高级字段：深度思考消耗 (R1 / o1 模型)
        reasoning_tokens = 0
        c_details = getattr(usage, "completion_tokens_details", None)
        if c_details:
            reasoning_tokens = getattr(c_details, "reasoning_tokens", 0)

        with self._data_lock:
            if date_str not in self._pending_deltas:
                self._pending_deltas[date_str] = {}
            if hash_key not in self._pending_deltas[date_str]:
                self._pending_deltas[date_str][hash_key] = {
                    "model": model_name,
                    "api_key": masked_key,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "cached_tokens": 0,
                    "completion_tokens": 0,
                    "reasoning_tokens": 0,
                    "total_tokens": 0,
                    "total_duration_s": 0.0,
                }

            stats = self._pending_deltas[date_str][hash_key]
            stats["calls"] += 1
            stats["prompt_tokens"] += p_tokens
            stats["cached_tokens"] += cached_tokens
            stats["completion_tokens"] += c_tokens
            stats["reasoning_tokens"] += reasoning_tokens
            stats["total_tokens"] += t_tokens
            stats["total_duration_s"] += round(duration, 3)

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

            # 转成 HashMap 方便合并
            disk_map = {f"{d['model']}|{d['api_key']}": d for d in disk_data}

            # 2. 将内存增量累加进去
            for hash_key, delta in items.items():
                if hash_key in disk_map:
                    disk_map[hash_key]["calls"] += delta["calls"]
                    disk_map[hash_key]["prompt_tokens"] += delta["prompt_tokens"]
                    disk_map[hash_key]["cached_tokens"] += delta["cached_tokens"]
                    disk_map[hash_key]["completion_tokens"] += delta[
                        "completion_tokens"
                    ]
                    disk_map[hash_key]["reasoning_tokens"] += delta["reasoning_tokens"]
                    disk_map[hash_key]["total_tokens"] += delta["total_tokens"]
                    disk_map[hash_key]["total_duration_s"] = round(
                        disk_map[hash_key]["total_duration_s"]
                        + delta["total_duration_s"],
                        3,
                    )
                else:
                    disk_map[hash_key] = delta.copy()

            # 3. 写回磁盘 (格式化保存)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(list(disk_map.values()), f, ensure_ascii=False, indent=2)

        # 4. 账本清零，重新开始下一轮记账
        self._pending_deltas.clear()
        self._last_flush = time.time()


# 暴露单例
usage_tracer = ModelUsageTracer()
