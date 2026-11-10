"""PARADIGM 路径符号解析与系统信息探测（纯函数）。"""

from __future__ import annotations

import os
import platform
import subprocess


def resolve_hook_path(
    path: str,
    *,
    plan_path: str | None,
    path_aliases: dict[str, str],
    extra_path_aliases: dict[str, str],
    agent_vm_dir: str,
    purrcat_dir: str,
    base_dir: str,
) -> str:
    """把 PARADIGM 里的路径符号/前缀解析成绝对路径。"""
    if path == "@PLAN" and plan_path:
        return plan_path
    if path.startswith("@"):
        aliases = {**path_aliases, **extra_path_aliases}
        if path in aliases:
            return aliases[path]
        # 前缀匹配：@ALIAS/sub/path → host/sub/path（供 @TASKSPACE/xxx 等用法）
        for alias, host in aliases.items():
            if path.startswith(alias + "/") or path.startswith(alias + "\\"):
                rest = path[len(alias) :].lstrip("/\\")
                return os.path.join(host, rest)
        return path
    if path.startswith(".purrcat/"):
        return os.path.join(purrcat_dir, path[len(".purrcat/") :])
    if path.startswith("src/"):
        return os.path.join(base_dir, path)
    if path == "/agent_vm" or path.startswith(("/agent_vm/", "/agent_vm\\")):
        # 兼容沙盒视角的绝对路径（/agent_vm/...），文件工具会做同样映射
        rel = path[len("/agent_vm") :].lstrip("/\\")
        return os.path.join(agent_vm_dir, rel)
    if path == "agent_vm" or path.startswith(("agent_vm/", "agent_vm\\")):
        # 不能用 lstrip("agent_vm")，它按字符集裁剪，会把 "agent_vm/x" 变成 "/x"，
        # 而 os.path.join 遇到以分隔符开头的片段会直接丢弃 AGENT_VM_DIR
        rel = path[len("agent_vm") :].lstrip("/\\")
        return os.path.join(agent_vm_dir, rel)
    return path


def get_gpu_info() -> str:
    """探测 GPU 型号：优先 nvidia-smi，Windows 回退 WMI，均失败返回未知。"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_VideoController).Name",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    except Exception:
        pass
    return "未知"


def get_system_info(agent_vm_dir: str) -> str:
    """@SYS：注入当前系统信息（操作系统/主机名/CPU/GPU + AgentVM 绝对路径）。"""
    lines = [
        "【当前系统信息】",
        f"- 操作系统: {platform.system()} {platform.release()} ({platform.machine()})",
        f"- 主机名: {platform.node()}",
        f"- CPU 核心数: {os.cpu_count() or '未知'}",
        f"- GPU: {get_gpu_info()}",
        f"- AgentVM 沙箱目录（绝对路径）: {agent_vm_dir}",
    ]
    return "\n".join(lines)
