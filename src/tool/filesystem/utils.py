import os
from src.tool.filesystem.exceptions import PermissionDeniedError


def load_blacklist():
    """加载配置中的黑名单路径"""
    from src.utils.config import get_file_config

    raw_list = get_file_config().get("dont_read_dirs", [])
    return [os.path.normcase(os.path.abspath(d)) for d in raw_list]


def check_allowed(path: str, blacklist: list) -> bool:
    """精准路径匹配，不误伤其他目录的同名文件夹"""
    path_norm = os.path.normcase(os.path.abspath(path))
    for rule_norm in blacklist:
        try:
            if os.path.commonpath([path_norm, rule_norm]) == rule_norm:
                return False
        except ValueError:
            pass
    return True


def resolve_safe_path(path: str) -> str:
    """
    处理路径映射：
    1. 如果以 /agent_vm 开头，映射到宿主机的 ./agent_vm 目录
    2. 检查路径是否在黑名单中
    3. 返回绝对路径
    """
    path = str(path).strip()

    if path.startswith("/agent_vm/") or path == "/agent_vm":
        rel_path = os.path.relpath(path, "/agent_vm") if path != "/agent_vm" else "."
        mount_point = os.path.abspath("./agent_vm")
        resolved_path = os.path.abspath(os.path.join(mount_point, rel_path))
    else:
        resolved_path = os.path.abspath(path)

    if not check_allowed(resolved_path, load_blacklist()):
        raise PermissionDeniedError(
            resolved_path, "安全策略拦截：此路径在系统黑名单中，禁止访问。"
        )

    return resolved_path
