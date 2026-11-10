"""Evolve 产物名称的安全校验。"""

import re

_INVALID_NAME = re.compile(r"[/\\:\x00-\x1f]")


def safe_name(name: str, label: str, strip_suffixes: tuple = ()) -> str:
    """校验并归一化产物名称；label 用于保持各类型原有错误文案。"""
    base = (name or "").strip()
    for suffix in strip_suffixes:
        base = base.removesuffix(suffix)
    if not base or base in (".", ".."):
        raise ValueError(f"{label} 名称不能为空或非法")
    if _INVALID_NAME.search(base) or len(base) > 60:
        raise ValueError(f"{label} 名称包含不支持的字符")
    return base
