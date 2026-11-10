"""Bash 沙盒的纯协议构造与输出清洗。

不依赖 docker / pexpect，便于单测命令包装与参数归一化。
"""

from __future__ import annotations

import os
import re
import sys

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def build_exec_command(
    docker_path: str, container_name: str, platform: str | None = None
) -> str:
    """Windows 无 TTY 用 -i，其余平台保留 -it。"""
    target = platform or sys.platform
    if target == "win32":
        return f"{docker_path} exec -i {container_name} /bin/bash"
    return f"{docker_path} exec -it {container_name} /bin/bash"


def build_shell_payload(safe_command: str, marker_str: str) -> str:
    """把命令包进代码块并强制 stdin 重定向，末尾打印退出码与 cwd 标记。"""
    return f'{{\n{safe_command}\n}} < /dev/null\necho -e "\\n{marker_str}$?|$(pwd)"'


def strip_command_echo(cleaned_output: str, command: str) -> str:
    """去掉终端回显的命令行本身，只保留真实输出。"""
    lines = [
        line for line in cleaned_output.splitlines() if line.strip() != command.strip()
    ]
    return "\n".join(lines).strip()


def clean_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text).replace("\r", "")


def container_env() -> dict:
    """缓存目录统一指向容器 tmpfs，避免 pip/npm/uv 缓存写大可写层。"""
    return {
        "XDG_CACHE_HOME": "/tmp/.cache",
        "PIP_CACHE_DIR": "/tmp/.cache/pip",
        "UV_CACHE_DIR": "/tmp/.cache/uv",
        "npm_config_cache": "/tmp/.cache/npm",
        "YARN_CACHE_FOLDER": "/tmp/.cache/yarn",
    }


def normalize_mount_path(p: str) -> str:
    r"""挂载路径归一化：D:/x、d:/x、/d/x 统一成小写反斜杠形式。"""
    p = str(p).replace("/", os.sep)
    # Docker Desktop 偶尔记录成 /d/x 形式（盘符风格），转成 d:\x
    if len(p) >= 3 and p[0] == os.sep and p[1].isalpha() and p[2] == os.sep:
        p = p[1] + ":" + p[2:]
    return os.path.normpath(p).lower()
