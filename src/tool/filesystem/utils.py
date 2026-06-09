import os
from src.tool.filesystem.exceptions import PermissionDeniedError

def resolve_absolute_path(path: str) -> str:
    """处理路径映射：将沙盒路径 /agent_vm 映射为宿主机的 ./agent_vm"""
    path = str(path).strip()
    
    if path.startswith("/agent_vm/"):
        path = "./agent_vm/" + path[len("/agent_vm/"):]
    elif path == "/agent_vm":
        path = "./agent_vm"

    return os.path.abspath(path)

def get_path_permission(target_path: str) -> str:
    """
    核心：基于最长前缀匹配获取路径权限。
    返回值: 'blocked', 'readonly', 'writable'
    """
    target_norm = os.path.normcase(os.path.abspath(target_path))
    
    from src.utils.config import get_file_config
    config = get_file_config()
    perms = config.get("permissions", {})
    
    best_match_len = -1
    best_perm = config.get("default_permission", "readonly")

    for perm_type in ["blocked", "readonly", "writable"]:
        for p in perms.get(perm_type, []):
            rule_norm = os.path.normcase(os.path.abspath(p))
            try:
                if os.path.commonpath([target_norm, rule_norm]) == rule_norm:
                    if len(rule_norm) > best_match_len:
                        best_match_len = len(rule_norm)
                        best_perm = perm_type
            except ValueError:
                pass

    return best_perm

def require_read(path: str) -> str:
    """要求读权限 (readonly 或 writable 均可)"""
    resolved = resolve_absolute_path(path)
    perm = get_path_permission(resolved)
    if perm == "blocked":
        raise PermissionDeniedError(
            resolved, "安全策略拦截：该路径不可读。请使用 Request 工具申请 file_read 权限。"
        )
    return resolved

def require_write(path: str) -> str:
    """要求写权限 (必须是 writable)"""
    resolved = resolve_absolute_path(path)
    perm = get_path_permission(resolved)
    if perm == "blocked":
        raise PermissionDeniedError(
            resolved, "安全策略拦截：该路径不可读不可写。请使用 Request 工具申请 file_write 权限。"
        )
    if perm == "readonly":
        raise PermissionDeniedError(
            resolved, "安全保护：该路径当前仅可读，不可写。请使用 Request 工具申请 file_write 权限。"
        )
    return resolved

def is_readable(path: str) -> bool:
    """用于 list/search/glob 遍历目录时的快速过滤"""
    return get_path_permission(os.path.abspath(path)) != "blocked"