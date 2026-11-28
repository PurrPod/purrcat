import os

from src.utils import sandbox_mounts
from src.utils.config import AGENT_VM_DIR


def convert_sandbox_path(path: str) -> str:
    """
    将 Agent 视角的沙盒路径映射为宿主机的真实绝对路径。

    /agent_vm/... -> AGENT_VM_DIR/...
    /agent_vm     -> AGENT_VM_DIR
    /mount/<别名>/... -> 挂载配置中的宿主目录/...
    其他路径原样返回（仅做 abspath 规范化）。
    """
    path = str(path).strip().replace("\\", "/")

    # 容错：URL 解析后可能出现 //agent_vm/、//mount/
    if path.startswith("//agent_vm/"):
        path = path[1:]
    elif path.startswith("//mount/"):
        path = path[1:]

    if path.startswith("/agent_vm/"):
        path = os.path.join(AGENT_VM_DIR, path[len("/agent_vm/") :])
    elif path == "/agent_vm":
        path = AGENT_VM_DIR
    else:
        mounted = sandbox_mounts.resolve_mount_path(path)
        if mounted is not None:
            return mounted

    return os.path.abspath(path)
