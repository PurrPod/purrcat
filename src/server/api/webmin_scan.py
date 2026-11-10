"""web-minimal 插件的目录扫描与静态资源路径校验。

根目录由调用方注入，便于用 tmp_path 直接单测；路由层只负责传参。
"""

from __future__ import annotations

import os

from src.server.api.common import resolve_within
from src.utils._fs import read_json


def read_plugin_descriptor(plugin_dir: str) -> dict | None:
    """读取某插件文件夹的 plugin.json；不存在或非法则返回 None。"""
    data = read_json(os.path.join(plugin_dir, "plugin.json"))
    if isinstance(data, dict) and data.get("id"):
        data["dir"] = plugin_dir
        return data
    return None


def scan_plugins(root: str) -> dict:
    """扫描某个根目录下所有插件，返回 { plugin_id: descriptor }。"""
    result = {}
    if not os.path.isdir(root):
        return result
    for name in os.listdir(root):
        # 删除插件时目录被改名为 <id>.trash 留待恢复，扫描必须跳过，
        # 否则它会连同内部 plugin.json 被当作仍存在的插件重新列出。
        if name.endswith(".trash"):
            continue
        plugin_dir = os.path.join(root, name)
        if not os.path.isdir(plugin_dir):
            continue
        desc = read_plugin_descriptor(plugin_dir)
        if desc:
            result[desc["id"]] = desc
    return result


def scan_plugin_roots(roots_low_to_high) -> dict:
    """按优先级从低到高扫描多个根，同名插件依次覆盖。"""
    merged = {}
    for root in roots_low_to_high:
        merged.update(scan_plugins(root))
    return merged


def plugin_backend_info(plugin_dir: str) -> dict | None:
    """探测插件是否自带后端：有 server/server.js 则报告 kind='npm'。"""
    server_js = os.path.join(plugin_dir, "server", "server.js")
    if os.path.isfile(server_js):
        return {"kind": "npm"}
    return None


def _resolve_entry(plugin_id: str, rel_path: str, roots, predicate):
    for root in roots:
        if not os.path.isdir(root):
            continue
        plugin_dir = os.path.join(root, plugin_id)
        if not os.path.isdir(plugin_dir):
            continue
        target = resolve_within(plugin_dir, rel_path)
        # 沙箱校验：目标必须在插件根目录内
        if target is None:
            return None
        if predicate(target):
            return target
    return None


def resolve_plugin_file(plugin_id: str, rel_path: str, roots) -> str | None:
    """在多个插件根中定位插件文件，沙箱到插件目录内防路径穿越。"""
    return _resolve_entry(plugin_id, rel_path, roots, os.path.isfile)


def resolve_plugin_subdir(plugin_id: str, rel_path: str, roots) -> str | None:
    """在多个插件根中定位插件内目录（供列目录用，沙箱防穿越）。"""
    return _resolve_entry(plugin_id, rel_path, roots, os.path.isdir)


def resolve_plugin_dir(plugin_id: str, roots) -> str | None:
    """返回插件所在目录（按 roots 顺序优先）。"""
    for root in roots:
        target = os.path.join(root, plugin_id)
        if os.path.isdir(target):
            return target
    return None
