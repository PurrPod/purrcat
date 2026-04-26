"""
path_utils — 路径安全校验工具

确保所有文件操作都在项目根目录范围内，防止越界读写。
支持沙盒路径 → 本地路径自动转换。
"""

import os


def resolve_project_root(task) -> str:
    """从 task 实例获取项目根目录"""
    if hasattr(task, "project_root") and task.project_root:
        return os.path.abspath(task.project_root)
    return os.path.abspath(os.getcwd())


def _sandbox_to_host_path(file_path: str, project_root: str) -> str:
    """
    尝试将沙盒路径转换为宿主机项目路径。
    
    沙盒路径以 /agent_vm/ 开头时，自动映射到宿主机上 project_root 所在的实际位置。
    例如：
      - 沙盒路径: /agent_vm/cat-in-cup/src/main.py
      - project_root 在宿主机上是 /home/user/agent_vm/cat-in-cup/
      - 转换后: /home/user/agent_vm/cat-in-cup/src/main.py
    """
    if file_path.startswith("/agent_vm/"):
        # 从沙盒路径中剥离 /agent_vm/ 前缀得到相对路径
        rel = file_path[len("/agent_vm/"):]
        # 如果 project_root 也在 /agent_vm/ 下
        if project_root.startswith("/agent_vm/"):
            # 说明都在同个挂载目录下，直接用 project_root 拼
            candidate = os.path.join(project_root, rel)
            # 去掉可能的重复（当 rel 已经是 project_root 的子路径时）
            return os.path.abspath(candidate)
        else:
            # project_root 不在 /agent_vm/ 下，尝试找到 agent_vm 目录
            # 从 project_root 往上找，看哪个祖先目录下有 agent_vm
            ancestor = project_root
            while True:
                test_path = os.path.join(ancestor, "agent_vm", rel)
                if os.path.exists(test_path):
                    return os.path.abspath(test_path)
                parent = os.path.dirname(ancestor)
                if parent == ancestor:
                    break
                ancestor = parent
    return file_path


def validate_path(file_path: str, project_root: str) -> str:
    """
    校验并规范化文件路径，确保在 project_root 范围内。
    
    自动处理：
    - 沙盒路径（/agent_vm/...）到宿主机路径的转换
    - 相对路径到绝对路径的解析
    - 路径越界检查
    
    返回: 规范化后的绝对路径
    抛出: ValueError 如果路径越界或无效
    """
    if not file_path:
        raise ValueError("❌ 路径不能为空")

    # 展开 ~ 和变量
    expanded = os.path.expanduser(os.path.expandvars(file_path))
    
    project_root_real = os.path.realpath(os.path.abspath(project_root))

    # ── 沙盒路径自动转换 ──
    if expanded.startswith("/agent_vm/"):
        host_path = _sandbox_to_host_path(expanded, project_root_real)
        if host_path != expanded:
            # 发生了转换，校验转换后的路径
            abs_path = host_path
        else:
            abs_path = os.path.abspath(expanded)
    else:
        # 转为绝对路径
        if not os.path.isabs(expanded):
            abs_path = os.path.abspath(os.path.join(project_root_real, expanded))
        else:
            abs_path = os.path.abspath(expanded)

    # 规范化（解析 .. 和符号链接）
    try:
        abs_path = os.path.realpath(abs_path)
    except OSError:
        abs_path = os.path.abspath(abs_path)

    # 校验：必须在项目根目录内
    if not abs_path.startswith(project_root_real + os.sep) and abs_path != project_root_real:
        hint = ""
        if file_path.startswith("/agent_vm/"):
            hint = (
                f"\n💡 检测到你传入了沙盒路径（以 /agent_vm/ 开头）。"
                f"\n   当前项目根目录是 `{project_root_real}`。"
                f"\n   沙盒路径 `/agent_vm/...` 在宿主机上可能需要转换成相对于项目根目录的路径。"
                f"\n   建议改为相对路径或直接使用宿主机项目目录下的路径。"
            )
        raise ValueError(
            f"❌ 路径越界: `{file_path}` -> `{abs_path}`\n"
            f"   项目根目录: `{project_root_real}`\n"
            f"   文件操作不允许超出项目根目录范围"
            f"{hint}"
        )

    return abs_path


def ensure_parent_dir(file_path: str) -> bool:
    """
    确保文件所在的父目录存在，不存在则自动创建。
    返回 True 表示创建了目录，False 表示已存在。
    """
    parent = os.path.dirname(file_path)
    if not parent:
        return False
    if not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
        return True
    return False


def validate_path_optional(file_path: str, project_root: str) -> str | None:
    """可选的路径校验，失败时返回 None 而非抛出异常"""
    try:
        return validate_path(file_path, project_root)
    except ValueError:
        return None
