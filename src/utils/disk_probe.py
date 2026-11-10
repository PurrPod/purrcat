"""磁盘维护的只读观测：docker CLI / vhdx / 占盘 / 有效数据估算。"""

import ctypes
import glob
import json
import os
import shutil
import sys
import time

from src.utils._proc import find_docker_desktop_exe, run_text
from src.utils.config import get_enriched_env, get_global_settings
from src.utils.disk_metrics import (
    LIVE_CACHE_TTL,
    RUN_CACHE_TTL,
    SANDBOX_CONTAINER,
    parse_rfc3339,
    parse_size,
    sandbox_record,
)

_WIN = sys.platform == "win32"

_live_cache = {"at": 0.0, "value": None}
_run_cache = {"at": 0.0, "value": False}
_vhdx_cache = {"path": None}
_sandbox_cache = {"at": 0.0, "value": None}


def reset_live_cache() -> None:
    _live_cache["at"] = 0.0


def reset_run_cache() -> None:
    _run_cache["at"] = 0.0


def reset_vhdx_cache() -> None:
    _vhdx_cache["path"] = None


def reset_sandbox_cache() -> None:
    _sandbox_cache["at"] = 0.0


def docker_cli() -> str | None:
    return shutil.which("docker", path=get_enriched_env().get("PATH")) or shutil.which(
        "docker"
    )


def find_vhdx() -> str | None:
    """定位 Docker Desktop 的数据盘 vhdx（优先 settings.json 里手动指定的路径）"""
    if _vhdx_cache["path"] and os.path.isfile(_vhdx_cache["path"]):
        return _vhdx_cache["path"]

    override = str(get_global_settings().get("docker_vhdx_path") or "").strip()
    if override and os.path.isfile(override):
        _vhdx_cache["path"] = override
        return override

    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    candidates = []
    roots = [
        os.path.join(local, "Docker", "wsl"),
        os.path.join(local, "Docker", "wsl", "data"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for p in glob.glob(os.path.join(root, "**", "*.vhdx"), recursive=True):
            if p not in candidates:
                candidates.append(p)
    if not candidates:
        return None

    def _size(p):
        try:
            return os.path.getsize(p)
        except Exception:
            return 0

    best = max(candidates, key=_size)
    _vhdx_cache["path"] = best
    return best


def allocated_size(path: str) -> int:
    """文件在磁盘上的实际占用（vhdx 是稀疏文件，逻辑大小 ≠ 实际占盘）"""
    if _WIN:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_size = kernel32.GetCompressedFileSizeW
        get_size.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        get_size.restype = ctypes.c_ulong
        high = ctypes.c_ulong(0)
        low = get_size(str(path), ctypes.byref(high))
        if low == 0xFFFFFFFF and ctypes.get_last_error() != 0:
            raise OSError(ctypes.get_last_error(), "GetCompressedFileSizeW 失败")
        return (high.value << 32) + low
    st = os.stat(path)
    blocks = getattr(st, "st_blocks", 0)
    return blocks * 512 if blocks else st.st_size


def docker_running(docker: str | None) -> bool:
    if not docker:
        return False
    now = time.time()
    if now - _run_cache["at"] < RUN_CACHE_TTL:
        return _run_cache["value"]
    from src.utils.sandbox_setup import check_docker_running

    value = check_docker_running(docker)
    _run_cache["at"] = now
    _run_cache["value"] = value
    return value


def live_estimate(docker: str | None) -> int | None:
    """容器内有效数据估算（docker system df 各行的 Size 合计）。

    注意：这是**估算**，Docker 自身统计会包含部分可回收开销，可能略高于真实值；
    死空间比例按 0 下限截断，不会因高估出现负值。
    """
    if not docker:
        return None
    now = time.time()
    if now - _live_cache["at"] < LIVE_CACHE_TTL:
        return _live_cache["value"]
    total = 0
    try:
        r = run_text(
            [docker, "system", "df", "--format", "{{json .}}"],
            timeout=20,
        )
        if r.returncode != 0:
            return None
        for line in (r.stdout or "").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            total += parse_size(str(row.get("Size") or ""))
    except Exception:
        return None
    _live_cache["at"] = now
    _live_cache["value"] = total
    return total


def sandbox_info(docker: str | None) -> dict | None:
    """沙盒容器创建时间/镜像（缓存 2 分钟，避免每次轮询都 spawn docker）"""
    if not docker:
        return None
    now = time.time()
    if now - _sandbox_cache["at"] < 120:
        return _sandbox_cache["value"]
    value = None
    try:
        r = run_text(
            [
                docker,
                "inspect",
                SANDBOX_CONTAINER,
                "--format",
                "{{.Created}}|{{.Config.Image}}",
            ],
            timeout=12,
        )
        if r.returncode == 0:
            created, _, image = (r.stdout or "").strip().partition("|")
            ts = parse_rfc3339(created)
            if ts:
                value = sandbox_record(image, ts, now)
    except Exception:
        value = None
    _sandbox_cache["at"] = now
    _sandbox_cache["value"] = value
    return value


__all__ = [
    "allocated_size",
    "docker_cli",
    "docker_running",
    "find_docker_desktop_exe",
    "find_vhdx",
    "live_estimate",
    "reset_live_cache",
    "reset_run_cache",
    "reset_sandbox_cache",
    "reset_vhdx_cache",
    "sandbox_info",
]
