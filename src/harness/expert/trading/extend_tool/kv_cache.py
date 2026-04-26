"""
Trading Expert KV Cache (对话级缓存)

目标：减少重复的模型 API 调用，降低推理成本。
原理：对 prompt + 上下文做 hash，命中则直接返回缓存结果。

特性：
- LRU 淘汰（最大条目数）
- TTL 过期（默认 1 小时）
- 内存 + 磁盘双写（断点恢复用）
- Thread-safe
"""

import json
import os
import threading
import time
import hashlib
from collections import OrderedDict
from typing import Any, Optional

from src.utils.config import DATA_DIR

CACHE_DIR = os.path.join(DATA_DIR, "kv_cache", "trading")
os.makedirs(CACHE_DIR, exist_ok=True)


class ConversationKVCache:
    """对话级 KV 缓存，用于缓存模型回复以减少 API 调用"""

    def __init__(self, max_entries: int = 500, default_ttl: int = 3600):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max = max_entries
        self._ttl = default_ttl
        self._lock = threading.Lock()
        self._hit = 0
        self._miss = 0

    def _make_key(self, system_prompt: str, messages: list, tools_sig: str = "") -> str:
        """生成缓存 key：对完整上下文做 hash"""
        ctx = json.dumps({
            "system": system_prompt[-500:],  # 只取末尾 500 字（system prompt 通常很长但稳定）
            "messages": messages[-10:],       # 最近 10 条对话
            "tools": tools_sig,
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(ctx).hexdigest()

    def get(self, system_prompt: str, messages: list, tools_sig: str = "") -> Optional[str]:
        """获取缓存。如果命中且未过期，返回缓存内容"""
        key = self._make_key(system_prompt, messages, tools_sig)
        with self._lock:
            if key not in self._cache:
                self._miss += 1
                return None
            entry = self._cache[key]
            if time.time() - entry["_time"] > self._ttl:
                del self._cache[key]
                self._miss += 1
                return None
            self._cache.move_to_end(key)
            self._hit += 1
            return entry["data"]

    def set(self, system_prompt: str, messages: list, response: str, tools_sig: str = ""):
        """写入缓存"""
        key = self._make_key(system_prompt, messages, tools_sig)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            while len(self._cache) >= self._max:
                self._cache.popitem(last=False)
            self._cache[key] = {
                "data": response,
                "_time": time.time(),
            }

    def persist(self):
        """持久化到磁盘（断点恢复用）"""
        with self._lock:
            data = {k: v for k, v in self._cache.items()}
        path = os.path.join(CACHE_DIR, "kv_cache.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[KVCache] persist failed: {e}")

    def load(self):
        """从磁盘加载缓存"""
        path = os.path.join(CACHE_DIR, "kv_cache.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._cache.clear()
                for k, v in data.items():
                    if time.time() - v["_time"] <= self._ttl:
                        self._cache[k] = v
        except Exception as e:
            print(f"[KVCache] load failed: {e}")

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._cache),
                "max": self._max,
                "hit": self._hit,
                "miss": self._miss,
                "ratio": self._hit / max(1, self._hit + self._miss),
            }

    def clear(self):
        with self._lock:
            self._cache.clear()


# 全局单例
_GLOBAL_CACHE = ConversationKVCache()


def get_cache() -> ConversationKVCache:
    return _GLOBAL_CACHE
