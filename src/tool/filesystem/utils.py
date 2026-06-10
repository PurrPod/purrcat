import os
from pathlib import Path
from src.tool.filesystem.exceptions import PermissionDeniedError


def resolve_absolute_path(path: str) -> str:
    """处理路径映射：将沙盒路径 /agent_vm 映射为宿主机的 ./agent_vm"""
    path = str(path).strip()

    if path.startswith("/agent_vm/"):
        path = "./agent_vm/" + path[len("/agent_vm/") :]
    elif path == "/agent_vm":
        path = "./agent_vm"

    return os.path.abspath(path)


def get_path_permission(target_path: str) -> str:
    """
    核心：基于最长匹配原则，支持绝对路径前缀匹配 和 .gitignore 风格的通配符匹配。
    返回值: 'blocked', 'readonly', 'writable'
    """
    # 统一转换路径大小写（Windows 下忽略大小写，Linux 下保持）
    target_norm = os.path.normcase(os.path.abspath(target_path))
    target_path_obj = Path(target_norm)

    from src.utils.config import get_file_config

    config = get_file_config()
    perms = config.get("permissions", {})

    best_match_len = -1
    best_perm = config.get("default_permission", "readonly")

    for perm_type in ["blocked", "readonly", "writable"]:
        for rule in perms.get(perm_type, []):
            rule_norm = os.path.normcase(rule)
            is_match = False

            # 1. 保留原有逻辑：绝对路径的前缀匹配（向下兼容）
            if os.path.isabs(rule_norm):
                try:
                    if os.path.commonpath([target_norm, rule_norm]) == rule_norm:
                        is_match = True
                except ValueError:
                    pass

            # 2. .gitignore 风格通配符匹配
            if not is_match:
                # 关键逻辑：遍历当前文件及其所有父级目录，只要任意一级匹配上了规则就算命中
                # 这确保了如果拦截了 ".git" 目录，其子文件 ".git/config" 也会被拦截
                for current_node in [target_path_obj] + list(target_path_obj.parents):
                    if current_node.match(rule_norm):
                        is_match = True
                        break

            # 3. 权重计算（特异性）
            if is_match:
                # 默认权重为规则字符串的长度
                match_weight = len(rule_norm)
                
                # 🌟 终极防弹逻辑：如果规则和目标路径一模一样（通常是人类通过 Request 批准的绝对路径）
                # 直接赋予一个碾压级别的高权重，保证绝对优先！
                if rule_norm == target_norm:
                    match_weight += 10000
                
                if match_weight > best_match_len:
                    best_match_len = match_weight
                    best_perm = perm_type

    return best_perm


def require_read(path: str) -> str:
    """要求读权限 (readonly 或 writable 均可)"""
    resolved = resolve_absolute_path(path)
    perm = get_path_permission(resolved)
    if perm == "blocked":
        raise PermissionDeniedError(
            resolved,
            "安全策略拦截：该路径不可读。请使用 Request 工具申请 file_read 权限。",
        )
    return resolved


def require_write(path: str) -> str:
    """要求写权限 (必须是 writable)"""
    resolved = resolve_absolute_path(path)
    perm = get_path_permission(resolved)
    if perm == "blocked":
        raise PermissionDeniedError(
            resolved,
            "安全策略拦截：该路径不可读不可写。请使用 Request 工具申请 file_write 权限。",
        )
    if perm == "readonly":
        raise PermissionDeniedError(
            resolved,
            "安全保护：该路径当前仅可读，不可写。请使用 Request 工具申请 file_write 权限。",
        )
    return resolved


def is_readable(path: str) -> bool:
    """用于 list/search/glob 遍历目录时的快速过滤"""
    return get_path_permission(os.path.abspath(path)) != "blocked"
