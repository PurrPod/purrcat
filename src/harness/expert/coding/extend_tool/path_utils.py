"""
path_utils — 路径安全校验工具

确保所有文件操作都在项目根目录范围内，防止越界读写。
"""

import os


def resolve_project_root(task) -> str:
    """从 task 实例获取项目根目录"""
    if hasattr(task, "project_root") and task.project_root:
        return os.path.abspath(task.project_root)
    return os.path.abspath(os.getcwd())


def validate_path(file_path: str, project_root: str) -> str:
    """
    校验并规范化文件路径，确保在 project_root 范围内。
    
    返回: 规范化后的绝对路径
    抛出: ValueError 如果路径越界
    """
    if not file_path:
        raise ValueError("❌ 路径不能为空")

    # 展开 ~ 和变量
    expanded = os.path.expanduser(os.path.expandvars(file_path))
    
    # 转为绝对路径
    if not os.path.isabs(expanded):
        abs_path = os.path.abspath(os.path.join(project_root, expanded))
    else:
        abs_path = os.path.abspath(expanded)

    # 规范化（解析 .. 和符号链接）
    try:
        abs_path = os.path.realpath(abs_path)
    except OSError:
        abs_path = os.path.abspath(abs_path)

    project_root_real = os.path.realpath(project_root)

    # 校验：必须在项目根目录内
    if not abs_path.startswith(project_root_real + os.sep) and abs_path != project_root_real:
        raise ValueError(
            f"❌ 路径越界: `{file_path}` -> `{abs_path}`\n"
            f"   项目根目录: `{project_root_real}`\n"
            f"   文件操作不允许超出项目根目录范围"
        )

    return abs_path


def validate_path_optional(file_path: str, project_root: str) -> str | None:
    """可选的路径校验，失败时返回 None 而非抛出异常"""
    try:
        return validate_path(file_path, project_root)
    except ValueError:
        return None
