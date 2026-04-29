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


def _find_git_root(path: str) -> str:
    """向上查找最近的 .git 目录"""
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, timeout=10, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    # 手动向上查找
    current = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _load_allowed_dirs():
    """加载允许导出的目录列表"""
    from src.utils.config import get_filesystem_config
    raw_list = get_filesystem_config().get("allowed_export_dirs", [])
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

    # Git 快照：在目标目录所在的 git 仓库中做 commit
    target_dir = host_path if os.path.isdir(host_path) else os.path.dirname(host_path)
    git_dir = _find_git_root(target_dir)

    commit_msg = ""
    if git_dir:
        repo_name = os.path.basename(git_dir)
        subprocess.run(["git", "-C", git_dir, "add", "-A"], capture_output=True, timeout=30)
        result = subprocess.run(
            ["git", "-C", git_dir, "commit", "-m", f"auto-snapshot: export {os.path.basename(host_path)}"],
            capture_output=True, timeout=30, text=True
        )
        commit_msg = result.stdout.strip() or result.stderr.strip()
    else:
        # 没有 git 仓库，初始化一个新仓库
        subprocess.run(["git", "-C", target_dir, "init"], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", target_dir, "add", "-A"], capture_output=True, timeout=30)
        result = subprocess.run(
            ["git", "-C", target_dir, "commit", "-m", f"auto-snapshot: initial commit after export"],
            capture_output=True, timeout=30, text=True
        )
        commit_msg = result.stdout.strip() or result.stderr.strip()
        git_dir = target_dir

    return {
        "host_path": host_path,
        "sandbox_path": sandbox_path,
        "git_repo": git_dir,
        "git_commit": commit_msg[:200] if commit_msg else "",
        "message": f"文件已导出到宿主机: {host_path}\nGit 快照已记录 ({git_dir})"
    }