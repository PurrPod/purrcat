"""工具市场响应组装：注册表 payload、安装结果与 Sensor 配置合并。

只做数据结构变换，不触碰网络与磁盘，便于直接单测。
"""

from __future__ import annotations

from src.server.api.tools_registry import (
    extract_registry_graphs,
    extract_registry_items,
)


def group_mcp_tools(schemas) -> dict:
    """按 MCP server 分组，仅保留工具 name/description（保持 server 出现顺序）。"""
    result = {}
    for s in schemas:
        srv = s.get("server", "unknown")
        func = s.get("function", {})
        result.setdefault(srv, []).append(
            {
                "name": func.get("name", ""),
                "description": func.get("description", ""),
            }
        )
    return result


def _registry_payload(data, key: str, items) -> dict:
    is_dict = isinstance(data, dict)
    return {
        "version": data.get("version") if is_dict else None,
        "repository": data.get("repository") if is_dict else None,
        key: items,
    }


def sensor_registry_payload(data) -> dict:
    sensors = data.get("sensors", []) if isinstance(data, dict) else []
    return _registry_payload(data, "sensors", sensors)


def graph_registry_payload(data) -> dict:
    return _registry_payload(data, "graphs", extract_registry_graphs(data))


def ui_plugin_registry_payload(data) -> dict:
    return _registry_payload(data, "plugins", extract_registry_items(data, "plugins"))


def agentloop_registry_payload(data) -> dict:
    return _registry_payload(
        data, "agentloops", extract_registry_items(data, "agentloops")
    )


def skill_install_response(skill_name: str) -> dict:
    return {
        "status": "success",
        "message": f"Skill '{skill_name}' 下载成功并已热加载入内存！",
    }


def skill_batch_response(installed: list, failed: list) -> dict:
    message = f"批量安装完成：成功 {len(installed)} 个"
    if failed:
        message += f"，失败 {len(failed)} 个"
    return {
        "status": "partial" if failed else "success",
        "installed": installed,
        "failed": failed,
        "message": message,
    }


def mcp_install_response(tool_count: int, source_note: str) -> dict:
    return {
        "status": "success",
        "message": (
            "MCP 配置已合并并热加载成功！"
            f"当前系统共载入 {tool_count} 个工具。{source_note}"
        ),
    }


def heartbeat_payload(interval: int, active: bool, min_interval: int) -> dict:
    return {"interval": max(min_interval, interval), "active": active}


def merge_sensor_entry(sensor: dict, existing_entry) -> dict:
    """合并 Sensor 配置：用户已填的非空 env 优先，registry 其余字段原样保留。"""
    existing_entry = existing_entry if isinstance(existing_entry, dict) else {}

    merged_env = {}
    new_env = sensor.get("env") or {}
    old_env = existing_entry.get("env") or {}
    if isinstance(new_env, dict) and isinstance(old_env, dict):
        for k, v in new_env.items():
            old_v = old_env.get(k)
            # 老值非空（非空字符串/非 None）则保留，否则用新的默认占位
            merged_env[k] = old_v if old_v not in (None, "") else v
        # 保留老配置中存在但 registry 已不再声明的自定义 env
        for k, v in old_env.items():
            if k not in merged_env:
                merged_env[k] = v

    merged = {
        "enabled": existing_entry.get(
            "enabled",
            bool(sensor.get("enabled", False)) if "enabled" in sensor else False,
        ),
        "env": merged_env,
    }
    # 其余 registry 字段原封不动保留一份（方便调试/回查；
    # capabilities 为旧架构字段，已废弃不落盘）
    for k, v in sensor.items():
        if k not in ("enabled", "env", "name", "capabilities"):
            merged[k] = v
    return merged
