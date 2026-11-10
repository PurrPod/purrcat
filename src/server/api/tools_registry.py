"""工具市场注册表：发布地址、条目提取、依赖归一化与本地已安装扫描。

这里只做数据与只读扫描，不发网络请求、不写磁盘，便于直接单测。
"""

from __future__ import annotations

import os

from src.server.api.common import (
    normalize_dependency_list as _normalize_dependency_list,
    normalize_registry_items,
)
from src.server.api.webmin import DEP_TYPES, SANDBOX_PLUGIN_ROOT, USER_PLUGIN_ROOT

REMOTE_REQUEST_TIMEOUT = 15

SENSORS_REGISTRY_URL = (
    "https://raw.githubusercontent.com/PurrPod/sensors/main/registry.json"
)
GRAPHS_REGISTRY_URL = (
    "https://raw.githubusercontent.com/PurrPod/graphs/main/registry.json"
)
# 传感器代码位于官方仓库 sensors/ 子目录下：sensors/<name>/<name>.py（如 feishu-bot）
SENSORS_CODE_BASE = "https://raw.githubusercontent.com/PurrPod/sensors/main/sensors"
GRAPHS_CODE_BASE = "https://raw.githubusercontent.com/PurrPod/graphs/main/graphs"

MCP_REGISTRY_URL = "https://raw.githubusercontent.com/PurrPod/mcps/main/registry.json"
SKILL_REGISTRY_URL = (
    "https://raw.githubusercontent.com/PurrPod/skills/main/registry.json"
)
# UI 插件（极简模式 webmin 插件系统）官方发布源
UI_PLUGIN_REGISTRY_URL = (
    "https://raw.githubusercontent.com/PurrPod/ui-plugins/main/registry.json"
)
UI_PLUGIN_CODE_BASE = (
    "https://raw.githubusercontent.com/PurrPod/ui-plugins/main/plugins"
)
# Agent Loop（PARADIGM 范式）官方发布源
AGENTLOOP_REGISTRY_URL = (
    "https://raw.githubusercontent.com/PurrPod/agentloops/main/registry.json"
)
AGENTLOOP_CODE_BASE = (
    "https://raw.githubusercontent.com/PurrPod/agentloops/main/agentloops"
)

# 裸仓库链接的默认分支探测候选（API 查询失败时按此顺序兜底试下载）
DEFAULT_BRANCH_CANDIDATES = ("main", "master")


def default_branch_candidates(branch: str, default_branch: str) -> list:
    """显式分支只试自己；裸仓库链接先试默认分支，再按候选兜底。"""
    candidates = []
    if branch:
        candidates.append(branch)
    else:
        if default_branch:
            candidates.append(default_branch)
        candidates += [b for b in DEFAULT_BRANCH_CANDIDATES if b not in candidates]
    return candidates


def extract_registry_graphs(data) -> list:
    """从 registry 数据中提取 graphs 列表（兼容裸数组或 {graphs: [...]}）。"""
    return normalize_registry_items(data, "graphs")


def extract_registry_items(data, *keys) -> list:
    """从 registry 数据中提取条目列表（兼容裸数组与显式 key / items / data）。"""
    return normalize_registry_items(data, *keys)


def normalize_dependency_list(raw) -> list:
    """按宿主插件依赖白名单归一化 [{type,id}]。"""
    return _normalize_dependency_list(raw, DEP_TYPES)


def scan_installed_ui_plugins(roots=None) -> list:
    """列出可写根下已安装的 UI 插件（含 plugin.json，跳过 <id>.trash）。"""
    names = set()
    search_roots = (
        roots if roots is not None else (USER_PLUGIN_ROOT, SANDBOX_PLUGIN_ROOT)
    )
    for root_dir in search_roots:
        if not os.path.isdir(root_dir):
            continue
        for name in os.listdir(root_dir):
            if name.endswith(".trash"):
                continue
            if os.path.isfile(os.path.join(root_dir, name, "plugin.json")):
                names.add(name)
    return sorted(names)


def scan_installed_agentloops(paradigms_dir: str) -> list:
    """列出 paradigms 目录下已安装的 AgentLoop 名字（去掉 .yaml/.yml 后缀）。"""
    names = []
    if not os.path.isdir(paradigms_dir):
        return names
    for f in sorted(os.listdir(paradigms_dir)):
        if f.endswith((".yaml", ".yml")):
            names.append(os.path.splitext(f)[0])
    return names


def installed_sensor_entries(config, extension_dir: str) -> list:
    """把 activate_sensor.json 归一化为市场「已安装」列表。"""
    installed = []
    for name, entry in (config or {}).items():
        installed.append(
            {
                "name": name,
                "enabled": bool(entry.get("enabled", False))
                if isinstance(entry, dict)
                else False,
                "has_code": os.path.exists(os.path.join(extension_dir, f"{name}.py")),
            }
        )
    return installed


def installed_graph_names(entries) -> list:
    """从 list_graphs() 结果提取去重排序后的图名。"""
    names = {
        entry["name"]
        for entry in entries
        if isinstance(entry, dict) and entry.get("name")
    }
    return sorted(names)
