"""utils 内部共用的子进程调用包装。"""

import os
import subprocess
import sys
import threading


def subprocess_encoding() -> str:
    return "gbk" if sys.platform == "win32" else "utf-8"


def run_text(
    cmd: list,
    timeout: float | None = None,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """执行命令并捕获输出，异常/超时由调用方处理。"""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding=subprocess_encoding(),
        errors="replace",
        env=env,
    )


def run_stream(
    cmd: list,
    log,
    timeout: float | None = None,
    env: dict | None = None,
) -> int:
    """执行命令，stdout/stderr 逐行交给 log；返回退出码（异常/超时返回 -1）。"""
    encoding = subprocess_encoding()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=encoding,
            errors="replace",
            bufsize=1,
            env=env,
        )
    except Exception as e:
        log(f"[!] 启动命令失败: {cmd[0]}: {e}")
        return -1

    def _pump():
        try:
            for line in proc.stdout:
                log(line.rstrip())
        except Exception:
            pass

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        log(f"[!] 超时（{int(timeout)}秒），已终止")
        return -1
    reader.join(timeout=5)
    return proc.returncode


def docker_desktop_candidates() -> list:
    return [
        r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Docker\Docker Desktop.exe"),
    ]


def find_docker_desktop_exe() -> str | None:
    for path in docker_desktop_candidates():
        if os.path.isfile(path):
            return path
    return None
