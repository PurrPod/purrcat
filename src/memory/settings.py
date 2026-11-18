"""记忆系统的用户级配置（``~/.purrcat/memory.json``）。

只暴露真正需要用户调整的参数；置信度增量、锚点等内部常量仍留在代码里。
"""

from __future__ import annotations

import json
import os
import threading

from src.memory.purrmemo.core.schema import DECAY_HALF_LIFE_DAYS
from src.utils.config import CONFIG_VERSION_KEY, LATEST_CONFIG_VERSION, PURRCAT_DIR

MEMORY_CONFIG_PATH = os.path.join(PURRCAT_DIR, "memory.json")

# 默认值与允许范围（min, max）
DEFAULTS = {
    "event_retention_days": 90,
    "decay_half_life_days": DECAY_HALF_LIFE_DAYS,
}

RANGES = {
    "event_retention_days": (0, 3650),
    "decay_half_life_days": (1, 3650),
}

# 当前版本包含的字段，以及历史版本已废弃、迁移时需删除的字段
DEFAULT_KEYS = tuple(DEFAULTS)
DEPRECATED_KEYS = ("search_top_k", "min_experience_score")

_INT_KEYS = {"event_retention_days"}

_cache_lock = threading.Lock()
_cache_mtime = None
_cache_value = None


def _to_number(key: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{key} 必须是数字")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} 必须是数字")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{key} 必须是有限数字")
    return number


def _validate_one(key: str, value):
    minimum, maximum = RANGES[key]
    number = _to_number(key, value)
    if number < minimum or number > maximum:
        raise ValueError(f"{key} 必须在 {minimum} 到 {maximum} 之间")
    if key in _INT_KEYS:
        if int(number) != number:
            raise ValueError(f"{key} 必须是整数")
        return int(number)
    return round(number, 4)


def validate_memory_settings(raw) -> dict:
    """校验并补齐完整配置；非法值抛 ``ValueError``。"""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("配置必须是 JSON 对象")

    result = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:
            result[key] = _validate_one(key, raw[key])
    return result


def _read_file(path: str) -> tuple[float | None, dict]:
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError):
        return None, dict(DEFAULTS)

    result = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:
            try:
                result[key] = _validate_one(key, raw[key])
            except ValueError:
                # 单个字段损坏时回退默认值，不影响其它配置
                pass
    return mtime, result


def get_memory_settings(path: str | None = None) -> dict:
    """读取配置；默认路径按 mtime 缓存，用户保存后即时生效。"""
    global _cache_mtime, _cache_value

    if path is not None:
        _, value = _read_file(path)
        return value

    try:
        mtime = os.path.getmtime(MEMORY_CONFIG_PATH)
    except OSError:
        return dict(DEFAULTS)

    with _cache_lock:
        if _cache_value is not None and _cache_mtime == mtime:
            return dict(_cache_value)
        mtime, value = _read_file(MEMORY_CONFIG_PATH)
        _cache_mtime = mtime
        _cache_value = value
        return dict(value)


def save_memory_settings(raw, path: str | None = None) -> dict:
    """校验后原子写入配置文件，返回归一化结果。"""
    global _cache_mtime, _cache_value

    normalized = validate_memory_settings(raw)
    target = path or MEMORY_CONFIG_PATH
    directory = os.path.dirname(target)
    if directory:
        os.makedirs(directory, exist_ok=True)

    temp_path = f"{target}.tmp"
    payload = {**normalized, CONFIG_VERSION_KEY: LATEST_CONFIG_VERSION}
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, target)

    if path is None:
        with _cache_lock:
            _cache_mtime = None
            _cache_value = None
    return normalized
