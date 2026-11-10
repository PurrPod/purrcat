"""Sensor 子进程的低层控制：环境清洗、命令构造、整树击杀。

与编排（SensorManager）分离，便于在不启动真实进程的情况下单测环境构造。
"""

import os
import subprocess

_IS_WINDOWS = os.name == "nt"
# 非 Windows 解释器没有该常量，置 0 便于在 Linux/macOS 上单测 Windows 分支
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 父进程（桌面壳 venv）透传的 Python 环境变量，会让 uv 子进程解释器版本错配
PYTHON_ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)

DOWNLOAD_BASE = "https://raw.githubusercontent.com/PurrPod/sensors/main/sensors"


def sensor_command(script_path: str) -> list[str]:
    return ["uv", "run", script_path]


def build_sensor_env(base_env: dict, cfg: dict) -> dict:
    """清洗父进程 Python 环境变量并合并传感器自定义 env。"""
    env = dict(base_env)
    for key in PYTHON_ENV_KEYS:
        env.pop(key, None)
    env.update(cfg.get("env", {}))
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def candidate_urls(repo_base: str, name: str) -> list[str]:
    """官方仓库两种布局：sensors/<name>/<name>.py 与 sensors/<name>.py。"""
    return [f"{repo_base}/{name}/{name}.py", f"{repo_base}/{name}.py"]


def close_stdin(process) -> None:
    """显式关闭 stdin 写端：进程死后残留管道若交给 GC，flush 会报 OSError[Errno 22]。"""
    try:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
    except Exception:
        pass


def kill_process_tree(process) -> None:
    """整树击杀 sensor 进程。

    Windows 下 terminate() 只杀 uv 包装进程，会留下 sensor python 孤儿——孤儿 bot 会继续
    重连外部服务（如飞书 WS）抢占事件，且其 stdout 已无人监听，事件会被静默吞掉。
    """
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                creationflags=_CREATE_NO_WINDOW,
            )
        else:
            process.terminate()
    except Exception:
        pass
    close_stdin(process)
