"""
Docker 数据盘维护：只读观测 + 一键回收空洞

设计取舍（用户明确要求）：
  - 启动/轮询只做只读检测，不阻塞、不提权、不自动压缩；
  - 只在部署面板展示「vhdx 实际占盘 / 有效数据估算 / 空洞占比」；
  - 空洞占比超过阈值时提示，用户点按钮才执行压缩（一次 UAC 授权）；
  - 另有低频 `docker builder prune`，从源头降低 vhdx 增长速度。

本模块保留对外入口与后台任务编排；观测在 disk_probe、写操作在 disk_ops、
阈值与折算在 disk_metrics、任务状态在 disk_tasks。
"""

import os
import sys
import threading
import time

from src.utils.config import get_global_settings, save_global_setting
from src.utils.disk_metrics import (
    DEAD_RATIO_THRESHOLD,
    PRUNE_INTERVAL,
    evaluate_disk_usage,
    human_size,
    unknown_live_detail,
)
from src.utils.disk_ops import (
    compact_vhdx,
    prune_build_cache,
    rebuild_sandbox as _rebuild_sandbox,
    start_docker,
    stop_docker,
)
from src.utils.disk_probe import (
    allocated_size,
    docker_cli,
    docker_running,
    find_vhdx,
    live_estimate,
    reset_live_cache,
    sandbox_info,
)
from src.utils.disk_tasks import append_log as _log
from src.utils.disk_tasks import begin as _begin
from src.utils.disk_tasks import finish as _finish
from src.utils.disk_tasks import get_task

_WIN = sys.platform == "win32"


# ══════════════ 只读观测 ══════════════


def get_disk_status() -> dict:
    """只读状态：vhdx 占盘 / 有效数据估算 / 空洞比例 + 最近维护记录"""
    result = {
        "supported": False,
        "vhdx_path": None,
        "allocated": 0,
        "logical": 0,
        "live_estimate": None,
        "dead_bytes": 0,
        "dead_ratio": None,
        "threshold": DEAD_RATIO_THRESHOLD,
        "needs_compact": False,
        "docker_running": False,
        "sandbox": None,
        "last_prune_at": None,
        "last_compact_at": None,
        "detail": "仅支持 Windows + Docker Desktop (WSL2)",
        "task": get_task(),
    }
    if not _WIN:
        return result

    settings = get_global_settings()
    result["last_prune_at"] = settings.get("docker_prune_at")
    result["last_compact_at"] = settings.get("docker_compact_at")

    vhdx = find_vhdx()
    docker = docker_cli()
    result["docker_running"] = docker_running(docker)
    if result["docker_running"]:
        result["sandbox"] = sandbox_info(docker)
    if not vhdx:
        result["detail"] = "未找到 Docker 数据盘 vhdx（可能未安装 Docker Desktop）"
        return result

    result["supported"] = True
    result["vhdx_path"] = vhdx
    try:
        result["allocated"] = allocated_size(vhdx)
        result["logical"] = os.path.getsize(vhdx)
    except Exception as e:
        result["detail"] = f"读取 vhdx 大小时失败: {e}"
        return result

    live = live_estimate(docker) if result["docker_running"] else None
    usage = evaluate_disk_usage(result["allocated"], live)
    if usage is None:
        result["detail"] = unknown_live_detail(result["allocated"])
        return result

    result["live_estimate"] = usage.live
    result["dead_bytes"] = usage.dead
    result["dead_ratio"] = round(usage.ratio, 4)
    result["needs_compact"] = usage.needs_compact
    result["detail"] = usage.detail
    return result


# ══════════════ 一键回收（压缩 vhdx） ══════════════


def _compact_worker() -> None:
    was_running = False
    try:
        vhdx = find_vhdx()
        if not vhdx:
            _log("[!] 未找到 Docker 数据盘 vhdx")
            raise RuntimeError("未找到 vhdx")
        was_running = docker_running(docker_cli())
        before = allocated_size(vhdx)
        _log(f"[*] 当前占盘 {human_size(before)}: {vhdx}")

        stop_docker(_log)
        ok, message = compact_vhdx(vhdx)
        if not ok:
            _log(f"[!] {message}")
            if was_running:
                start_docker(_log)
            _finish("failed")
            return

        after = allocated_size(vhdx)
        freed = max(0, before - after)
        _log(
            f"[+] 压缩完成: {human_size(before)} → {human_size(after)}，释放 {human_size(freed)}"
        )
        save_global_setting("docker_compact_at", time.time())
        reset_live_cache()
        if was_running:
            start_docker(_log)
        _finish("success")
        return
    except Exception as e:
        _finish("failed")
        _log(f"[!] 压缩失败: {e}")
        try:
            if was_running and not docker_running(docker_cli()):
                start_docker(_log)
        except Exception:
            pass
        return


def start_compact() -> tuple[bool, str]:
    """用户点击「一键回收」后启动后台压缩；正在执行时拒绝重复触发"""
    if not _WIN:
        return False, "仅支持 Windows 下的 Docker Desktop"
    first_line = f"[{time.strftime('%H:%M:%S')}] 开始压缩 Docker 数据盘"
    if not _begin("compact", first_line):
        return False, "磁盘维护任务正在执行中，请稍候"
    threading.Thread(target=_compact_worker, daemon=True).start()
    return True, "压缩已开始，Docker 会短暂停止"


# ══════════════ 构建缓存清理（预防膨胀） ══════════════


def start_prune() -> tuple[bool, str]:
    """手动触发一次构建缓存清理（后台线程）"""
    first_line = f"[{time.strftime('%H:%M:%S')}] 开始清理构建缓存"
    if not _begin("prune", first_line):
        return False, "磁盘维护任务正在执行中，请稍候"

    def _worker():
        ok = False
        try:
            ok = prune_build_cache(_log)
        except Exception as e:
            _log(f"[!] 清理异常: {e}")
        _finish("success" if ok else "failed")

    threading.Thread(target=_worker, daemon=True).start()
    return True, "已开始清理构建缓存"


def maybe_weekly_prune() -> None:
    """启动后台调用：距离上次清理超过 7 天才执行一次，失败不更新时间戳"""
    try:
        last = get_global_settings().get("docker_prune_at") or 0
        if time.time() - float(last) < PRUNE_INTERVAL:
            return
        docker = docker_cli()
        if not docker or not docker_running(docker):
            return
        if get_task()["state"] == "running":
            return
        prune_build_cache(_log)
    except Exception as e:
        print(f"[DiskMaintenance] 定期清理构建缓存失败(忽略): {e}")


def rebuild_sandbox() -> tuple[bool, str]:
    """删除沙盒容器（薄委托，保留原入口）。"""
    return _rebuild_sandbox()
