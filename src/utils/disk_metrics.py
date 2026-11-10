"""磁盘维护的纯策略：单位换算、时间解析、空洞与压缩判定。"""

import datetime
import re
from dataclasses import dataclass

from src.utils._format import human_bytes, parse_size

# 空洞占比提示阈值（0.30 = 30%）
DEAD_RATIO_THRESHOLD = 0.30
# 空洞绝对值低于 1GB 时不打扰用户（小盘占比再高也没回收价值）
DEAD_MIN_BYTES = 1 << 30
# docker system df 结果缓存秒数（前端 3s 轮询，避免频繁 spawn docker）
LIVE_CACHE_TTL = 60
# docker info 活性检查缓存秒数
RUN_CACHE_TTL = 15
# 构建缓存自动清理周期
PRUNE_INTERVAL = 7 * 24 * 3600
SANDBOX_CONTAINER = "agent_computer"

human_size = human_bytes

__all__ = [
    "DEAD_RATIO_THRESHOLD",
    "DEAD_MIN_BYTES",
    "LIVE_CACHE_TTL",
    "RUN_CACHE_TTL",
    "PRUNE_INTERVAL",
    "SANDBOX_CONTAINER",
    "DiskUsage",
    "evaluate_disk_usage",
    "human_size",
    "parse_rfc3339",
    "parse_size",
    "sandbox_record",
    "unknown_live_detail",
]


@dataclass(frozen=True)
class DiskUsage:
    allocated: int
    live: int
    dead: int
    ratio: float
    needs_compact: bool
    detail: str


def parse_rfc3339(text: str) -> float | None:
    """解析 docker 的 Created 时间（纳秒精度），失败返回 None"""
    m = re.match(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})",
        text or "",
    )
    if not m:
        return None
    frac = (m.group(2) or "")[:6].ljust(6, "0")
    tz = "+00:00" if m.group(3) == "Z" else m.group(3)
    try:
        dt = datetime.datetime.fromisoformat(f"{m.group(1)}.{frac}{tz}")
        return dt.timestamp()
    except Exception:
        return None


def evaluate_disk_usage(allocated: int, live: int | None) -> DiskUsage | None:
    """把「实际占盘 + 有效数据」折算为空洞指标；无有效数据估算时返回 None。"""
    if live is None:
        return None
    live = min(live, allocated)
    dead = max(0, allocated - live)
    ratio = (dead / allocated) if allocated else 0.0
    needs_compact = ratio >= DEAD_RATIO_THRESHOLD and dead >= DEAD_MIN_BYTES
    detail = (
        f"实际占盘 {human_size(allocated)} · "
        f"有效数据约 {human_size(live)} · "
        f"空洞约 {human_size(dead)}（{ratio * 100:.0f}%）"
    )
    return DiskUsage(
        allocated=allocated,
        live=live,
        dead=dead,
        ratio=ratio,
        needs_compact=needs_compact,
        detail=detail,
    )


def unknown_live_detail(allocated: int) -> str:
    return (
        f"数据盘实际占盘 {human_size(allocated)}，Docker 未运行，暂时无法估算有效数据"
    )


def sandbox_record(image: str, created_at: float, now: float) -> dict:
    return {
        "image": image,
        "created_at": created_at,
        "age_days": round((now - created_at) / 86400, 1),
    }
