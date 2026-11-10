"""Server API 层共用的小工具：JSON 读写、错误映射、路径安全与注册表归一化。

只放跨模块复用的纯逻辑/薄封装；具体业务语义仍留在各自 router 模块。
"""

from __future__ import annotations

import json
import os
import traceback
from typing import Any

from fastapi import HTTPException

from src.utils._fs import read_json


def save_json_file(path: str, data: Any, log_prefix: str = "[Config API]") -> bool:
    """写入缩进 JSON；失败时只记录日志并返回 False。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"{log_prefix} 保存配置文件失败 {path}: {e}")
        return False


def read_json_file(path: str, default: Any = None) -> Any:
    """读取 JSON；文件缺失、损坏或读取失败时返回 default。"""
    return read_json(path, default)


def unexpected_error(
    prefix: str, exc: Exception, status_code: int = 500
) -> HTTPException:
    """把未预期异常映射为 HTTPException；调用方照常 ``raise``。"""
    traceback.print_exc()
    return HTTPException(status_code=status_code, detail=f"{prefix}{exc}")


def is_unsafe_name(name: str) -> bool:
    """目录名/文件名白名单：空串、路径分隔符与上跳片段一律拒绝。"""
    return not name or any(c in name for c in ("/", "\\", ".."))


def safe_basename(raw: Any) -> str:
    """取最后一段名字并统一为 / 分隔；Windows 反斜杠也视作分隔符。"""
    return os.path.basename(str(raw or "").replace("\\", "/"))


def is_unsafe_relative_path(rel: str) -> bool:
    """注册表文件清单防御：绝对路径或以 .. 上跳的片段均非法。"""
    norm = str(rel or "").replace("\\", "/")
    return norm.startswith("/") or ".." in norm.split("/")


def is_within_root(root: str, path: str) -> bool:
    """path 是否位于 root 内（含跨盘符时安全返回 False）。"""
    try:
        abs_root = os.path.abspath(root)
        return os.path.commonpath([abs_root, os.path.abspath(path)]) == abs_root
    except ValueError:
        return False


def resolve_within(root: str, rel: str) -> str | None:
    """把相对路径解析到 root 内；越界（含跨盘符）返回 None。"""
    rel_path = str(rel or "").replace("\\", "/").lstrip("/")
    abs_root = os.path.abspath(root)
    abs_target = (
        os.path.abspath(os.path.join(abs_root, rel_path)) if rel_path else abs_root
    )
    try:
        if os.path.commonpath([abs_root, abs_target]) != abs_root:
            return None
    except ValueError:
        return None
    return abs_target


def normalize_registry_items(data: Any, *keys: str) -> list:
    """从注册表数据提取条目列表，兼容裸数组与 {<key>|items|data: [...]}。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in tuple(keys) + ("items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def normalize_dependency_list(raw: Any, allowed_types: tuple) -> list:
    """归一化依赖清单：只保留白名单类型，统一为 {"type","id"}。"""
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        dep_type = str(item.get("type") or "").strip()
        dep_id = str(item.get("id") or "").strip()
        if dep_type in allowed_types and dep_id:
            out.append({"type": dep_type, "id": dep_id})
    return out
