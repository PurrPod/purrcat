import os
from pathlib import Path
from src.tool.filesystem.exceptions import PermissionDeniedError
from src.utils.config import AGENT_VM_DIR, PROJECTS_DIR
from src.utils.path import convert_sandbox_path

# 沙盒根目录（预计算，用于快速放行）
_AGENT_VM_ROOT = os.path.normcase(os.path.abspath(AGENT_VM_DIR))
# 项目根目录与记忆文件名（预计算，用于严格匹配项目记忆文件）
_PROJECTS_ROOT = os.path.normcase(os.path.abspath(PROJECTS_DIR))
_MEMORY_FILENAME = os.path.normcase("MEMORY.md")


def is_project_memory_path(path: str) -> bool:
    """判断是否为某个项目的记忆文件：<PROJECTS_DIR>/<project_xxx>/MEMORY.md

    必须严格匹配目录层级与文件名，避免把任意位置的 MEMORY.md 一并放行。
    """
    try:
        norm = os.path.normcase(os.path.abspath(path))
        if os.path.commonpath([norm, _PROJECTS_ROOT]) != _PROJECTS_ROOT:
            return False
    except ValueError:  # Windows 下跨盘符等情况
        return False

    parts = os.path.relpath(norm, _PROJECTS_ROOT).split(os.sep)
    return (
        len(parts) == 2
        and parts[0].startswith("project_")
        and parts[1] == _MEMORY_FILENAME
    )


def is_in_agent_vm(path: str) -> bool:
    """判断路径是否位于 agent 沙盒内（agent 自己的电脑，权限全开）"""
    try:
        return (
            os.path.commonpath(
                [os.path.normcase(os.path.abspath(path)), _AGENT_VM_ROOT]
            )
            == _AGENT_VM_ROOT
        )
    except ValueError:  # Windows 下跨盘符等情况
        return False


def _rule_matches(target_norm: str, target_path_obj: Path, rule: str) -> bool:
    rule_norm = os.path.normcase(rule)
    if os.path.isabs(rule_norm):
        try:
            return os.path.commonpath([target_norm, rule_norm]) == rule_norm
        except ValueError:
            return False
    for current_node in [target_path_obj] + list(target_path_obj.parents):
        if current_node.match(rule_norm):
            return True
    return False


def _default_permission(config: dict) -> str:
    value = str(config.get("default_permission") or "readonly")
    if value in ("writable", "readwrite"):
        return "readwrite"
    if value in ("none", "blocked"):
        return "blocked"
    if value == "writeonly":
        return "writeonly"
    return "readonly"


def get_path_permission(target_path: str) -> str:
    """
    先判定 blocked；未命中时按全局默认权限计算读写能力。
    返回值: 'blocked', 'readonly', 'writeonly', 'readwrite'
    """
    # 沙盒内是 agent 自己的电脑，无论用户是否配置权限，一律全放行
    if is_in_agent_vm(target_path):
        return "readwrite"

    # 项目记忆文件由 Agent 维护，读写都直接放行（严格匹配项目目录下的 MEMORY.md）
    if is_project_memory_path(target_path):
        return "readwrite"

    target_norm = os.path.normcase(os.path.abspath(target_path))
    target_path_obj = Path(target_norm)

    from src.utils.config import get_file_config

    config = get_file_config()
    perms = config.get("permissions", {})
    if not isinstance(perms, dict):
        perms = {}

    for rule in perms.get("blocked", []) or []:
        if _rule_matches(target_norm, target_path_obj, str(rule)):
            return "blocked"

    default = _default_permission(config)
    allow_read = default in ("readonly", "readwrite")
    allow_write = default in ("writeonly", "readwrite")

    if not allow_read:
        allow_read = any(
            _rule_matches(target_norm, target_path_obj, str(rule))
            for rule in perms.get("readonly", []) or []
        )
    if not allow_write:
        allow_write = any(
            _rule_matches(target_norm, target_path_obj, str(rule))
            for rule in perms.get("writable", []) or []
        )

    if allow_read and allow_write:
        return "readwrite"
    if allow_read:
        return "readonly"
    if allow_write:
        return "writeonly"
    return "blocked"


def can_read(path: str) -> bool:
    return get_path_permission(path) in ("readonly", "readwrite")


def can_write(path: str) -> bool:
    return get_path_permission(path) in ("writeonly", "readwrite")


def require_read(path: str) -> str:
    """要求读权限"""
    resolved = convert_sandbox_path(path)
    if not can_read(resolved):
        raise PermissionDeniedError(
            resolved,
            "安全策略拦截：该路径不可读。请使用 Request 工具申请 file_read 权限。",
        )
    return resolved


def require_write(path: str) -> str:
    """要求写权限"""
    resolved = convert_sandbox_path(path)
    if not can_write(resolved):
        raise PermissionDeniedError(
            resolved,
            "安全保护：该路径不可写。请使用 Request 工具申请 file_write 权限。",
        )
    return resolved


def is_readable(path: str) -> bool:
    """用于 list/search/glob 遍历目录时的快速过滤"""
    return can_read(os.path.abspath(path))
