"""文件导入功能 - 将宿主机文件/目录导入沙盒工作区"""

import os
import shutil
import time

from src.tool.filesystem.exceptions import (
    HostPathNotFoundError,
    PermissionDeniedError,
    FileTooLargeError,
    DirectoryTooLargeError,
    UnsupportedPathTypeError
)


def _load_blacklist():
    """将配置中的相对路径（如 src/）绑定为当前项目的绝对路径，并消除大小写/斜杠差异"""
    from src.utils.config import get_file_config
    raw_list = get_file_config().get("dont_read_dirs", [])
    return [os.path.normcase(os.path.abspath(d)) for d in raw_list]


def _is_denied(path: str, blacklist: list) -> bool:
    """精准路径匹配，不误伤其他目录的同名文件夹"""
    path_norm = os.path.normcase(os.path.realpath(path))

    for rule_norm in blacklist:
        try:
            if os.path.commonpath([path_norm, rule_norm]) == rule_norm:
                return True
        except ValueError:
            pass
    return False


def import_file(host_path: str, sandbox_dir: str = "imports") -> dict:
    """
    将宿主机文件/目录导入沙盒工作区

    安全检查：
    - 禁止导入 dont_read_dirs 内的文件
    - 导入上级目录时，黑名单内的子文件/子目录自动跳过
    - 目录导入有 30MB 总大小限制
    - 防御软链接绕过 (Symlink Bypass)
    - 防御目标路径穿越 (Path Traversal)

    Args:
        host_path: 宿主机上文件/目录的绝对路径
        sandbox_dir: 沙盒内的目标目录（相对于 /agent_vm/），默认 imports

    Returns:
        包含 sandbox_path, host_path, message 的字典
    """
    host_path = os.path.realpath(host_path)

    # 路径存在性检查
    if not os.path.exists(host_path):
        raise HostPathNotFoundError(host_path)

    # 加载黑名单
    blacklist = _load_blacklist()

    # 根路径检查
    if _is_denied(host_path, blacklist):
        raise PermissionDeniedError(host_path, f"路径在黑名单内\n黑名单: {blacklist}")

    # 检查上级目录内是否包含黑名单路径
    skipped_dirs = []
    skipped_files = 0

    sandbox_dir = sandbox_dir.replace("\\", "/").strip()
    if sandbox_dir.startswith("/agent_vm/"):
        sandbox_subdir = sandbox_dir[len("/agent_vm/"):]
    elif sandbox_dir.startswith("agent_vm/"):
        sandbox_subdir = sandbox_dir[len("agent_vm/"):]
    elif sandbox_dir in ["/agent_vm", "agent_vm"]:
        sandbox_subdir = ""
    else:
        sandbox_subdir = sandbox_dir

    sandbox_subdir = sandbox_subdir.strip()

    # 确定挂载点和目标绝对路径
    mount_point = os.path.abspath("./agent_vm")
    dest_dir = os.path.abspath(os.path.join(mount_point, sandbox_subdir) if sandbox_subdir else mount_point)
    if os.path.commonpath([mount_point, dest_dir]) != mount_point:
        raise PermissionDeniedError(sandbox_dir, "目标路径越权：不允许将文件导入到沙箱外部！")

    os.makedirs(dest_dir, exist_ok=True)

    MAX_SIZE = 30 * 1024 * 1024  # 30MB
    sandbox_path = ""
    msg = ""

    if os.path.isfile(host_path):
        # 单文件导入
        fname = os.path.basename(host_path)
        file_size = os.path.getsize(host_path)
        if file_size > MAX_SIZE:
            raise FileTooLargeError(host_path, file_size / 1024 / 1024)

        shutil.copy2(host_path, os.path.join(dest_dir, fname))
        base_path = f"/agent_vm/{sandbox_subdir}" if sandbox_subdir else "/agent_vm"
        sandbox_path = f"{base_path}/{fname}"
        msg = f"文件已导入沙盒: {sandbox_path} ({file_size / 1024:.1f}KB)"

    elif os.path.isdir(host_path):
        # 目录导入：先走一遍计算总大小 + 检查黑名单
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(host_path):
            # 检查当前目录是否在黑名单内
            if _is_denied(dirpath, blacklist):
                skipped_dirs.append(dirpath)
                dirnames.clear()
                filenames.clear()
                continue
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                if _is_denied(fp, blacklist):
                    skipped_files += 1
                    continue
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    pass
                if total_size > MAX_SIZE:
                    raise DirectoryTooLargeError(host_path)

        # 正式复制，同样跳过黑名单
        def _ignore_denied(src, names):
            ignored = set()
            for name in names:
                full = os.path.join(src, name)
                if _is_denied(full, blacklist):
                    ignored.add(name)
            return ignored

        dirname = os.path.basename(host_path.rstrip("/\\"))
        dest_path = os.path.join(dest_dir, dirname)
        if os.path.exists(dest_path):
            dest_path = os.path.join(dest_dir, f"{dirname}_{int(time.time())}")

        shutil.copytree(host_path, dest_path, symlinks=False, ignore=_ignore_denied)
        base_path = f"/agent_vm/{sandbox_subdir}" if sandbox_subdir else "/agent_vm"
        sandbox_path = f"{base_path}/{os.path.basename(dest_path)}"

        msg = f"目录已导入沙盒: {sandbox_path} ({total_size / 1024 / 1024:.1f}MB)"
        if skipped_dirs or skipped_files:
            msg += f"\n⚠️ 导入文件内含不可读名单（{blacklist}）内的文件，已被跳过，如有需要，请联系老板开启权限"

    else:
        raise UnsupportedPathTypeError(host_path)

    return {
        "sandbox_path": sandbox_path,
        "host_path": host_path,
        "message": msg
    }