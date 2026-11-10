"""模型用量统计的纯函数：字段提取、增量累加、磁盘账本合并。

与单例/定时刷盘解耦，便于直接单测。
"""

from datetime import datetime

SUMMARY_FIELDS = (
    "prompt_tokens",
    "cached_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "total_tokens",
)


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "UNKNOWN"
    if len(api_key) <= 10:
        return "***"
    return f"{api_key[:6]}***{api_key[-4:]}"


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def extract_usage_fields(usage) -> dict:
    """对齐 OpenAI SDK v1.x，提取缓存与思考 Token。"""
    cached_tokens = 0
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details:
        cached_tokens = getattr(prompt_details, "cached_tokens", 0)

    reasoning_tokens = 0
    completion_details = getattr(usage, "completion_tokens_details", None)
    if completion_details:
        reasoning_tokens = getattr(completion_details, "reasoning_tokens", 0)

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "cached_tokens": cached_tokens,
        "completion_tokens": getattr(usage, "completion_tokens", 0),
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": getattr(usage, "total_tokens", 0),
    }


def empty_bucket(model_name: str, masked_key: str) -> dict:
    return {
        "model": model_name,
        "api_key": masked_key,
        "calls": 0,
        **{field: 0 for field in SUMMARY_FIELDS},
        "total_duration_s": 0.0,
    }


def apply_delta(bucket: dict, fields: dict, duration: float) -> None:
    bucket["calls"] += 1
    for field in SUMMARY_FIELDS:
        bucket[field] += fields.get(field, 0)
    bucket["total_duration_s"] += round(duration, 3)


def merge_into_disk(disk_data: list, items: dict) -> list:
    """把内存增量按 `model|api_key` 合并进磁盘账本，返回新列表。"""
    disk_map = {f"{d['model']}|{d['api_key']}": d for d in disk_data}
    for hash_key, delta in items.items():
        if hash_key in disk_map:
            target = disk_map[hash_key]
            target["calls"] += delta["calls"]
            for field in SUMMARY_FIELDS:
                target[field] += delta[field]
            target["total_duration_s"] = round(
                target["total_duration_s"] + delta["total_duration_s"], 3
            )
        else:
            disk_map[hash_key] = delta.copy()
    return list(disk_map.values())
