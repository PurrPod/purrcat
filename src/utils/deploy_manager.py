"""
部署中心：运行环境依赖的状态检测与一键安装
配置中心「部署」标签页的后端支撑：
  - check_all()    各依赖项（uv / node / sandbox / embedding）当前就绪状态
  - start_deploy() 后台线程执行单项安装，日志收集在内存
  - get_overview() 就绪状态 + 任务进度合并视图（前端轮询）
安装完成后依赖注册表 PATH 变更（get_enriched_env 可立即感知），
但主程序完整生效仍建议重启（前端会提示）。
"""

import threading
import time

from src.utils.deploy_installers import INSTALLERS
from src.utils.deploy_probe import check_all
from src.utils.deploy_tasks import (
    DEPLOY_ITEMS,
    append_log,
    begin,
    finish,
    snapshot,
)

__all__ = ["DEPLOY_ITEMS", "check_all", "get_overview", "start_deploy"]


def start_deploy(item: str) -> tuple[bool, str]:
    """启动单项部署（后台线程）；已在运行中则拒绝。返回 (ok, message)"""
    if item not in DEPLOY_ITEMS:
        return False, f"未知部署项: {item}"
    first_line = f"[{time.strftime('%H:%M:%S')}] 开始部署 {item}"
    if not begin(item, first_line):
        return False, "该依赖正在部署中，请在日志中查看进度"

    def _worker():
        try:
            ok = INSTALLERS[item](item)
        except Exception as e:
            ok = False
            append_log(item, f"[!] 部署异常: {e}")
        finish(item, ok)
        append_log(
            item,
            "[+] 部署成功，重启程序后生效"
            if ok
            else "[!] 部署失败，可根据日志排查后重试",
        )

    threading.Thread(target=_worker, daemon=True).start()
    return True, "部署已启动"


def get_overview() -> dict:
    """前端轮询视图：各依赖项就绪状态 + 部署任务进度与日志"""
    items = check_all()
    tasks = snapshot()
    try:
        from src.utils.disk_maintenance import get_disk_status

        disk = get_disk_status()
    except Exception as e:
        disk = {"supported": False, "detail": f"磁盘状态检测失败: {e}"}
    return {"items": items, "tasks": tasks, "disk": disk}
