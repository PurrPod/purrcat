"""文件导出功能 - 将沙盒内文件/目录导出到宿主机"""

import os
import shutil
import subprocess
import time

from src.tool.filesystem.exceptions import (
    SandboxPathNotFoundError,
    ExportDirNotAllowedError,
    GitNotAvailableError,
    PermissionDeniedError
)


def _load_allowed_dirs():
    """加载允许导出的目录列表"""
    from src.utils.config import get_file_config
    raw_list = get_file_config().get("allowed_export_dirs", [])
    return [os.path.normcase(os.path.abspath(d)) for d in raw_list]


def export_file(sandbox_path: str, host_path: str) -> dict:
    """
    将沙盒内文件/目录导出到宿主机（带安全检查 + Git 快照）

    安全机制：
    - 只允许导出到 allowed_export_dirs
    - 导出前自动创建 Git 快照（init + add + commit）
    - 本地无 git 工具则拒绝导出

    Args:
        sandbox_path: 沙盒内文件/目录路径（必须以 /agent_vm/ 开头）
        host_path: 宿主机目标路径

    Returns:
        包含 host_path, sandbox_path, git_repo, git_commit, message 的字典
    """
    sandbox_path = sandbox_path.strip()

    # 路径格式检查
    if not sandbox_path.startswith("/agent_vm/"):
        raise PermissionDeniedError(sandbox_path, "禁止导出沙盒外的文件")

    # 转换为宿主机路径
    rel_path = os.path.relpath(sandbox_path, "/agent_vm")
    mount_point = os.path.abspath("./agent_vm")
    host_src = os.path.abspath(os.path.join(mount_point, rel_path))

    # 检查源文件是否存在
    if not os.path.exists(host_src):
        raise SandboxPathNotFoundError(sandbox_path)

    # 检查目标路径是否在允许列表内
    host_path_norm = os.path.normcase(os.path.abspath(host_path))
    allowed_dirs = _load_allowed_dirs()

    is_allowed = False
    for rule_norm in allowed_dirs:
        try:
            if os.path.commonpath([host_path_norm, rule_norm]) == rule_norm:
                is_allowed = True
                break
        except ValueError:
            pass

    if not is_allowed:
        raise ExportDirNotAllowedError(host_path, allowed_dirs)

    # 检查 git 是否可用
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        raise GitNotAvailableError()

    # 写入目标文件
    os.makedirs(os.path.dirname(host_path), exist_ok=True)
    if os.path.isfile(host_src):
        shutil.copy2(host_src, host_path)
    elif os.path.isdir(host_src):
        dest = host_path
        if os.path.exists(dest):
            dest = f"{host_path}_{int(time.time())}"
        shutil.copytree(host_src, dest, symlinks=False)
        host_path = dest

    # Git 快照：在允许导出的目录中进行 git init 和 commit
    git_dir = None
    for rule_norm in allowed_dirs:
        try:
            if os.path.commonpath([host_path_norm, rule_norm]) == rule_norm:
                git_dir = rule_norm
                break
        except ValueError:
            pass

    commit_msg = ""
    if git_dir:
        git_dir_existed = os.path.isdir(os.path.join(git_dir, ".git"))
        if not git_dir_existed:
            subprocess.run(["git", "-C", git_dir, "init"], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", git_dir, "add", "-A"], capture_output=True, timeout=30)
        if git_dir_existed:
            result = subprocess.run(
                ["git", "-C", git_dir, "commit", "-m", f"auto-snapshot: export {os.path.basename(host_path)}"],
                capture_output=True, timeout=30, text=True
            )
            commit_msg = result.stdout.strip() or result.stderr.strip()
        else:
            result = subprocess.run(
                ["git", "-C", git_dir, "commit", "-m", f"auto-snapshot: initial commit after export"],
                capture_output=True, timeout=30, text=True
            )
            commit_msg = result.stdout.strip() or result.stderr.strip()

    return {
        "host_path": host_path,
        "sandbox_path": sandbox_path,
        "git_repo": git_dir,
        "git_commit": commit_msg[:200] if commit_msg else "",
        "message": f"文件已导出到宿主机: {host_path}\nGit 快照已记录 ({git_dir})"
    }