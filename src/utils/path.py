import os

from src.utils.config import AGENT_VM_DIR


def convert_sandbox_path(path: str) -> str:
    """
    将 Agent 视角的沙盒路径映射为宿主机的真实绝对路径。

    /agent_vm/... -> AGENT_VM_DIR/...
    /agent_vm     -> AGENT_VM_DIR
    其他路径原样返回（仅做 abspath 规范化）。
    """
    path = str(path).strip().replace("\\", "/")

    # 容错：URL 解析后可能出现 //agent_vm/
    if path.startswith("//agent_vm/"):
        path = path[1:]

    if path.startswith("/agent_vm/"):
        path = os.path.join(AGENT_VM_DIR, path[len("/agent_vm/") :])
    elif path == "/agent_vm":
        path = AGENT_VM_DIR

    return os.path.abspath(path)
