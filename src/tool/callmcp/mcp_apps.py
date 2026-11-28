"""MCP Apps 旁路存储：发现 UI 资源、按 tool_call_id 落盘、历史消息标注。

HTML 与调用元数据分文件存放：历史接口每轮轮询只读小 JSON，
体积可达数 MB 的 App HTML 仅在 iframe 真正渲染时才取。
"""

from __future__ import annotations

import json
import os
import re

from src.utils.config import BUFFER_DIR

APP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def ui_resource_uri(tool_meta) -> str | None:
    """从工具的 `_meta` 中取 `ui.resourceUri`（兼容扁平的 `ui/resourceUri`）。"""
    if not isinstance(tool_meta, dict):
        return None
    ui = tool_meta.get("ui")
    uri = ui.get("resourceUri") if isinstance(ui, dict) else None
    if not uri:
        uri = tool_meta.get("ui/resourceUri")
    return uri if isinstance(uri, str) and uri.strip() else None


def is_mcp_app_mime(mime: str | None) -> bool:
    """MCP App 资源 MIME 为 text/html（可带 profile=mcp-app）。"""
    if not isinstance(mime, str):
        return False
    return mime.split(";")[0].strip().lower() == "text/html"


def is_legal_app_id(app_id) -> bool:
    return isinstance(app_id, str) and bool(APP_ID_RE.match(app_id))


def _apps_dir() -> str:
    return os.path.join(BUFFER_DIR, "mcp_apps")


def _json_path(app_id: str) -> str:
    return os.path.join(_apps_dir(), f"{app_id}.json")


def _html_path(app_id: str) -> str:
    return os.path.join(_apps_dir(), f"{app_id}.html")


def _result_path(app_id: str) -> str:
    return os.path.join(_apps_dir(), f"{app_id}.result.json")


def save_app(app_id: str, payload: dict, html: str) -> bool:
    """落盘一个 MCP App；id 非法或写失败返回 False。"""
    if not is_legal_app_id(app_id) or not isinstance(html, str):
        return False
    try:
        os.makedirs(_apps_dir(), exist_ok=True)
        with open(_html_path(app_id), "w", encoding="utf-8") as f:
            f.write(html)
        with open(_json_path(app_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[MCP App] 保存失败 {app_id}: {e}")
        return False


def has_app(app_id: str) -> bool:
    return is_legal_app_id(app_id) and os.path.exists(_json_path(app_id))


def load_payload(app_id: str) -> dict | None:
    if not has_app(app_id):
        return None
    try:
        with open(_json_path(app_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_html(app_id: str) -> str | None:
    if not is_legal_app_id(app_id):
        return None
    try:
        with open(_html_path(app_id), "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def save_result(tool_call_id: str, payload: dict) -> bool:
    """落盘无 UI 工具的调用结果，供聊天页用宿主组件兜底渲染。"""
    if not is_legal_app_id(tool_call_id) or not isinstance(payload, dict):
        return False
    try:
        os.makedirs(_apps_dir(), exist_ok=True)
        with open(_result_path(tool_call_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[MCP App] 保存结果失败 {tool_call_id}: {e}")
        return False


def load_result(app_id: str) -> dict | None:
    if not is_legal_app_id(app_id):
        return None
    try:
        with open(_result_path(app_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def attach_history_apps(messages: list[dict]) -> list[dict]:
    """给有旁路文件的 tool 消息附加 `mcp_app` / `mcp_data`，返回新列表（不改入参）。"""
    out = []
    for message in messages or []:
        if message.get("role") != "tool":
            out.append(message)
            continue
        app_id = message.get("tool_call_id")
        if not is_legal_app_id(app_id):
            out.append(message)
            continue
        payload = load_payload(app_id)
        data = load_result(app_id)
        if not payload and not data:
            out.append(message)
            continue
        marked = dict(message)
        if payload:
            marked["mcp_app"] = {
                "id": app_id,
                "server": payload.get("server", ""),
                "tool": payload.get("tool", ""),
                "uri": payload.get("uri", ""),
            }
        if data:
            marked["mcp_data"] = data
        out.append(marked)
    return out
