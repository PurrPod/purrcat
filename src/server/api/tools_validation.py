"""工具市场请求校验：GitHub URL、名称白名单、文件清单与 MCP 配置 JSON。

全部为纯函数（除 HTTPException 外无副作用），便于直接单测。
"""

from __future__ import annotations

import json
import re

from fastapi import HTTPException

from src.server.api.common import (
    is_unsafe_relative_path,
    safe_basename,
)


def parse_skill_github_url(url: str):
    """解析 GitHub 链接，返回 (owner, repo, branch, path)；不匹配则抛 400。

    支持三种写法：
    - 裸仓库链接 `https://github.com/owner/repo`（skill 目录即仓库根）
    - 目录链接 `https://github.com/owner/repo/tree/<branch>/path/to/skill`
    - 文件链接 `https://github.com/owner/repo/blob/<branch>/path/SKILL.md`（取其所在文件夹）

    裸仓库链接无法从 URL 得知分支，branch 返回空串，由 fetch_repo_zip 探测默认分支。
    """
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/(?:tree|blob)/([^/]+)(?:/(.*))?", url
    )
    if match:
        owner, repo, branch, path = match.groups()
        path = (path or "").strip("/")
        # 链接指向具体文件（如 SKILL.md）时，skill 目录取其所在文件夹
        if path and "." in path.split("/")[-1]:
            path = "/".join(path.split("/")[:-1])
        return owner, repo, branch, path

    # 裸仓库链接（允许尾斜杠与 .git 后缀）
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if match:
        owner, repo = match.groups()
        return owner, repo, "", ""

    raise HTTPException(
        status_code=400,
        detail=(
            "URL格式错误！支持仓库根链接 `https://github.com/owner/repo`，"
            "或目录/文件链接 `https://github.com/owner/repo/tree/<branch>/path/to/skill`"
        ),
    )


def require_non_empty(raw, detail: str) -> str:
    """strip 后必须非空，否则 400。"""
    value = str(raw or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail=detail)
    return value


def require_plain_name(raw, detail: str) -> str:
    """strip 后必须是单段名字（不含 / \\ ..），否则 400。"""
    value = str(raw or "").strip()
    if not value or any(c in value for c in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail=detail)
    return value


def safe_install_name(raw, empty_detail: str, invalid_detail: str) -> str:
    """取最后一段作为落盘目录名；空值或 . / .. 分别映射到指定错误。"""
    value = require_non_empty(raw, empty_detail)
    safe_name = safe_basename(value)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail=invalid_detail)
    return safe_name


def safe_path_component(raw, detail: str) -> str:
    """取最后一段作为依赖安装目录名；空值或 . / .. 统一映射到 detail。"""
    safe_name = safe_basename(raw)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail=detail)
    return safe_name


def validate_registry_files(
    files, *, detail_prefix: str = "注册表文件清单含非法路径"
) -> list:
    """校验注册表声明的相对文件路径，返回原列表（非法项直接 502）。"""
    for rel in files:
        if is_unsafe_relative_path(rel):
            raise HTTPException(status_code=502, detail=f"{detail_prefix}: {rel}")
    return list(files)


def parse_mcp_config_json(config_json: str) -> dict:
    """解析用户粘贴的 MCP 配置；JSON 非法或缺少 mcpServers 顶层键时 400。"""
    try:
        data = json.loads(config_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400, detail="输入的不是合法的 JSON 格式，请检查语法"
        )
    if "mcpServers" not in data:
        raise HTTPException(
            status_code=400, detail="JSON 格式必须以 'mcpServers' 为顶层键"
        )
    return data


def ui_plugin_root_dir(raw_root, root_to_dir: dict, user_root: str) -> str:
    """把插件声明的 root 映射为落盘根目录；builtin 不接受市场安装。"""
    key = str(raw_root or "").strip().lower()
    if key == "builtin":
        raise HTTPException(
            status_code=400, detail="内置插件随 App 分发，不支持从市场安装"
        )
    return root_to_dir.get(key) or user_root
