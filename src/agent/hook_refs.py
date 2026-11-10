"""Hook 参数中 @引用的展开与内容解析（纯函数）。"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

PLAN_FALLBACK = "暂无 BrainStorm 计划"


def build_ref_re(aliases) -> re.Pattern:
    return re.compile("|".join(re.escape(alias) for alias in aliases))


def expand_refs(value, resolve, ref_re: re.Pattern):
    """把 @引用 展开成具体内容；单次左到右替换，展开结果不会被再次解析。"""

    def sub(matched):
        text = resolve(matched.group(0))
        return matched.group(0) if text is None else text

    if isinstance(value, str):
        return ref_re.sub(sub, value)
    if isinstance(value, dict):
        return {k: expand_refs(v, resolve, ref_re) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_refs(v, resolve, ref_re) for v in value]
    return value


def resolve_ref_content(
    alias: str,
    kwargs: dict,
    cache: dict,
    *,
    path_aliases: dict[str, str],
    extra_content_aliases: dict[str, str],
    system_info: Callable[[], str],
    plan_reader: Callable[[Any], str],
) -> str | None:
    """取 @引用的展开内容；取不到时返回 None，保留原始 @符号。"""
    if alias in cache:
        return cache[alias]

    text = None
    if alias == "@USERQUERY":
        if "received_messages" in kwargs:
            text = "\n".join(
                str(msg.get("content", ""))
                for msg in (kwargs.get("received_messages") or [])
                if msg.get("type") == "user"
            )
    elif alias == "@SYS":
        text = system_info()
    elif alias == "@PLAN":
        text = plan_reader(kwargs.get("agent")) or PLAN_FALLBACK
    elif alias in extra_content_aliases:
        # 动态别名（如 @TASKSPACE）：直接展开为注册内容，不读文件
        text = extra_content_aliases[alias]
    else:
        path = path_aliases.get(alias)
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
            except Exception:
                text = None

    cache[alias] = text
    return text
