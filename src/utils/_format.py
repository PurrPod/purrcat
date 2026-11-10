"""utils 内部共用的大小与时间格式化。"""

import datetime
import re

_UNIT_SCALE = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "PB": 1000**5,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}


def parse_size(text: str) -> int:
    """解析 docker 输出里的容量文本（1.5GB / 2KiB），失败返回 0。"""
    m = re.match(r"^\s*([\d.]+)\s*([KMGTP]?i?B)\s*$", text or "", re.I)
    if not m:
        return 0
    return int(float(m.group(1)) * _UNIT_SCALE.get(m.group(2).upper(), 1))


def human_bytes(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def format_hms(timestamp: float | int | None) -> str:
    if not timestamp:
        return "??:??:??"
    return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def format_datetime(timestamp: float | int, pattern: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.datetime.fromtimestamp(timestamp).strftime(pattern)
