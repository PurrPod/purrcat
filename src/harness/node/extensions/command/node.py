import asyncio
import platform
import subprocess
from typing import Any, Dict

from src.harness.node.base import BaseNode


def _host_os() -> str:
    """宿主机系统，归一化为 windows / linux / mac"""
    sys = platform.system()
    if sys == "Windows":
        return "windows"
    if sys == "Darwin":
        return "mac"
    return "linux"


def _normalize(spec: str) -> str:
    spec = (spec or "").strip().lower()
    clean = spec.replace("_", "-")
    if clean in ("macos", "darwin", "mac"):
        return "mac"
    if clean in ("win", "windows", "win32", "win64"):
        return "windows"
    if clean in ("linux", "ubuntu", "debian", "centos", "alpine"):
        return "linux"
    return clean  # any / 空 / 未知


class Node(BaseNode):
    """命令执行节点：按指定目标 OS 在宿主机上执行命令行。

    若宿主机的系统与节点指定的目标 OS 不匹配，则不做任何执行，直接标记节点完成
    （输出 stdout 仅含说明文案），避免在错误平台上跑出意外副作用。
    """

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        # 连线输入即唯一来源（节点无面板配置输入框）
        cmd = self.unpack(inputs, "command", default=None)
        if cmd is None:
            cmd = ""
        if not isinstance(cmd, str):
            cmd = str(cmd)

        os_spec = self.unpack(inputs, "os", default=None)
        os_spec = _normalize(str(os_spec)) if os_spec is not None else "any"

        timeout = 120.0
        host = _host_os()

        if os_spec not in ("any", "", host):
            reason = f"目标OS=[{os_spec}] 不匹配宿主机=[{host}]，跳过执行"
            self.log(context, "SYSTEM", f"⏭️ [命令执行] {reason}")
            return {
                "stdout": self.pack(
                    f"[跳过] {reason}（命令未运行）", "string", "text/plain"
                ),
                "stderr": self.pack("", "string", "text/plain"),
                "exit_code": self.pack(0, "number", "application/json"),
                "skipped": self.pack(True, "boolean", "application/json"),
            }

        if not cmd.strip():
            self.log(context, "WARN", "⚠️ [命令执行] 命令为空，已标记完成")
            return {
                "stdout": self.pack("[空命令] 未执行任何命令行", "string", "text/plain"),
                "stderr": self.pack("", "string", "text/plain"),
                "exit_code": self.pack(0, "number", "application/json"),
                "skipped": self.pack(False, "boolean", "application/json"),
            }

        self.log(
            context,
            "SYSTEM",
            f"🚀 [命令执行] 宿主机={host} 目标OS={os_spec} 执行: {cmd[:200]}",
        )
        try:
            proc = await asyncio.to_thread(
                lambda: subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            )
        except subprocess.TimeoutExpired:
            self.log(
                context, "ERROR", f"⏰ [命令执行] 超时({timeout}s)已中止"
            )
            return {
                "stdout": self.pack("", "string", "text/plain"),
                "stderr": self.pack(f"[超时] 命令超过 {timeout}s 被中止", "string", "text/plain"),
                "exit_code": self.pack(-1, "number", "application/json"),
                "skipped": self.pack(False, "boolean", "application/json"),
            }

        self.log(
            context,
            "SYSTEM",
            f"✅ [命令执行] 退出码={proc.returncode} stdout={len(proc.stdout)}B stderr={len(proc.stderr)}B",
        )
        return {
            "stdout": self.pack(proc.stdout or "", "string", "text/plain"),
            "stderr": self.pack(proc.stderr or "", "string", "text/plain"),
            "exit_code": self.pack(proc.returncode, "number", "application/json"),
            "skipped": self.pack(False, "boolean", "application/json"),
        }