"""purrcat 工具 → ACP ToolKind / 标题 / locations / rawInput。"""

from __future__ import annotations

import json
import os

from src.tool.utils.token_limit import count_tokens

UPDATE_TOKEN_LIMIT = 2000

# ToolKind 枚举：read/edit/delete/move/search/execute/think/fetch/other
TOOL_KIND = {
    "Bash": "execute",
    "BrainStorm": "think",
    "Memo": "think",
    "Request": "fetch",
    "Fetch": "fetch",
    "Search": "search",
    "CallMCP": "other",
    "Cron": "other",
    "Task": "other",
    "KernelUpgrade": "other",
}

# FileSystem 按 action 细分（schema 枚举：list/read/edit/write/search/glob/move/copy/delete/undo）
FS_KIND = {
    "list": "read",
    "read": "read",
    "edit": "edit",
    "write": "edit",
    "search": "search",
    "glob": "search",
    "move": "move",
    "copy": "move",
    "delete": "delete",
    "undo": "other",
}


def tool_kind(name: str, args) -> str:
    """工具名+参数 → ToolKind（编辑器据此选图标/展示形态）"""
    if name == "FileSystem" and isinstance(args, dict):
        return FS_KIND.get(str(args.get("action", "")), "other")
    return TOOL_KIND.get(name, "other")


def tool_title(name: str, args) -> str:
    """人可读标题：工具名 + 关键参数摘要"""
    if isinstance(args, dict):
        if name == "FileSystem":
            action = str(args.get("action", "") or "fs")
            path = str(args.get("path", "") or args.get("destination", ""))
            base = os.path.basename(path.replace("\\", "/")) if path else ""
            return f"FileSystem {action} {base}".strip()
        if name == "Bash":
            return f"Bash {str(args.get('command', ''))[:60]}".strip()
        if name == "Search":
            return f"Search {str(args.get('query', ''))[:40]}".strip()
        if name == "CallMCP":
            return f"CallMCP {str(args.get('server_name', ''))[:30]}".strip()
        if name == "Memo":
            action = str(args.get("action", "") or "memo")
            if action == "search":
                q = (
                    (args.get("query") or {}).get("prompt", "")
                    if isinstance(args.get("query"), dict)
                    else ""
                )
                return f"Memo search {str(q)[:40]}".strip()
            return f"Memo {action}".strip()
    return name


def tool_locations(name: str, args) -> list:
    """follow-the-agent：涉及文件的工具报 locations（宿主机绝对路径）"""
    if name != "FileSystem" or not isinstance(args, dict):
        return []
    path = args.get("path") or args.get("destination")
    if not path:
        return []
    try:
        from src.utils.path import convert_sandbox_path

        return [{"path": convert_sandbox_path(str(path))}]
    except Exception:
        return []


def tool_raw(args) -> dict | None:
    """rawInput：参数对象原样透出（超 token 预算则省略，防撑爆编辑器）"""
    if not isinstance(args, dict) or not args:
        return None
    try:
        if count_tokens(json.dumps(args, ensure_ascii=False)) <= UPDATE_TOKEN_LIMIT:
            return args
    except Exception:
        pass
    return None


def vision_text_parts(parts: list) -> str:
    """vision 直注 parts → 纯文本占位（base64 不外泄）"""
    return "\n".join(
        str(p.get("text", ""))
        for p in parts
        if isinstance(p, dict) and p.get("type") == "text"
    )
