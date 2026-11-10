"""工具市场注册表查询与安装/卸载决策（纯逻辑，不做 IO）。

安装编排只依赖这里的判定结果，便于用普通字符串/字典直接单测。
"""

from __future__ import annotations

from fastapi import HTTPException


def missing_names(required, existing, *, ignore_case: bool = False) -> list:
    """按原顺序返回本地缺失的名字。

    MCP 配置键大小写敏感，Skill 目录名按小写比较，由 ignore_case 区分。
    """
    if ignore_case:
        existing_set = {str(n).lower() for n in (existing or [])}
        return [
            name
            for name in (str(n).strip() for n in (required or []))
            if name and name.lower() not in existing_set
        ]
    existing_set = set(existing or [])
    return [
        name
        for name in (str(n).strip() for n in (required or []))
        if name and name not in existing_set
    ]


def mcp_registry_entries(data) -> list:
    """从 MCP 注册表响应提取条目序列（兼容 {mcps: {...}}、{mcps: [...]} 与裸数组）。"""
    raw = data.get("mcps", []) if isinstance(data, dict) else data
    return list(raw.values()) if isinstance(raw, dict) else (raw or [])


def skill_registry_items(data) -> list:
    """从 Skill 注册表响应提取 (key, entry) 序列；仅 {skills: {...}} 结构有效。"""
    raw = data.get("skills", {}) if isinstance(data, dict) else {}
    return list(raw.items()) if isinstance(raw, dict) else list(enumerate(raw or []))


def find_mcp_entry(entries, name: str):
    """按单元名或 mcpServers 键名忽略大小写匹配注册表条目。"""
    lower = name.lower()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        servers = entry.get("mcpServers") or {}
        if str(entry.get("name", "")).lower() == lower or any(
            str(key).lower() == lower for key in servers
        ):
            return entry
    return None


def find_skill_entry(items, name: str):
    """按注册表键或 entry.name 忽略大小写匹配 Skill 条目。"""
    lower = name.lower()
    for key, entry in items or []:
        if not isinstance(entry, dict):
            continue
        if (
            str(key or "").lower() == lower
            or str(entry.get("name", "")).lower() == lower
        ):
            return entry
    return None


def resolve_mcp_dependencies(entries, missing) -> tuple[dict, list, list]:
    """把缺失 MCP 映射为 (待合并 servers, [(repo, [server])], 说明)。"""
    merged_servers = {}
    repo_server_pairs = []
    notes = []
    for name in missing:
        target = find_mcp_entry(entries, name)
        if not target or not target.get("mcpServers"):
            notes.append(f"MCP '{name}' 本地与市场均缺失，已跳过")
            continue
        merged_servers.update(target["mcpServers"])
        repo_server_pairs.append(
            (target.get("repo") or "", list(target["mcpServers"].keys()))
        )
    return merged_servers, repo_server_pairs, notes


def resolve_skill_install_plan(items, missing) -> tuple[list, list]:
    """把缺失 Skill 映射为 ([(name, link)], 说明)；市场无链接即记说明。"""
    plan = []
    notes = []
    for name in missing:
        target = find_skill_entry(items, name)
        link = (target or {}).get("skill-single-link") or ""
        if not link:
            notes.append(f"Skill '{name}' 本地与市场均缺失，已跳过")
            continue
        plan.append((name, link))
    return plan, notes


def required_files(raw_files, required: str) -> list:
    """归一化注册表文件清单，并保证核心描述文件位于首位。"""
    files = [str(f) for f in (raw_files or []) if str(f).strip()]
    if required not in files:
        files.insert(0, required)
    return files


def drop_mcp_server(config: dict, name: str) -> dict:
    """从配置中移除指定 MCP Server；不存在时按原语义返回 404。"""
    servers = config.get("mcpServers", {})
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"未配置 MCP Server '{name}'")
    del servers[name]
    return config
