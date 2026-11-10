"""工具执行器：进程内线程执行与子进程隔离执行。

隔离与否由调用方（route）按工具名单决定，本模块只负责执行与打断。
"""

from __future__ import annotations

import asyncio
import inspect
import multiprocessing
import queue
import threading
import time
from typing import Any

HARD_WALL_LIMIT_SECONDS = 30 * 60


def run_func_sync(target_func, arguments: dict) -> Any:
    """执行工具函数，支持同步和异步（工作线程/子进程内运行，无事件循环）"""
    if inspect.iscoroutinefunction(target_func):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio

            nest_asyncio.apply()
            return asyncio.get_event_loop().run_until_complete(target_func(**arguments))
        return asyncio.run(target_func(**arguments))

    return target_func(**arguments)


def process_worker(target_func, kwargs, result_queue):
    """子进程入口：执行工具并把结果/异常放回队列（模块级函数，可被 pickle）"""
    try:
        res = run_func_sync(target_func, kwargs)
        result_queue.put({"status": "success", "data": res})
    except BaseException as e:
        result_queue.put({"status": "error", "error": f"{type(e).__name__}: {e}"})


def interrupted_result() -> dict:
    """伪造的打断结果：返回给 LLM，告知执行已被人类打断"""
    return {
        "content": "【系统强制打断】工具执行已被人类打断，请停下你的工作接收新指令。",
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "warning",
            "snip": "⚡ 执行被人类打断",
        },
    }


def execute_inline(target_func, arguments: dict, cancel_event) -> Any:
    """进程内执行（守护线程 + 轮询）：轻量工具用，打断时放弃线程直接返回伪造结果"""
    holder = {}

    def _worker():
        try:
            holder["result"] = run_func_sync(target_func, arguments)
        except BaseException as e:
            holder["error"] = e

    t = threading.Thread(target=_worker, daemon=True, name="ToolInlineWorker")
    t.start()
    while True:
        if "result" in holder or "error" in holder:
            break
        if cancel_event is not None and cancel_event.is_set():
            # 放弃该守护线程（轻量工具毫秒级完成，极小概率泄漏），立刻让路
            return interrupted_result()
        t.join(timeout=0.2)
    if "error" in holder:
        raise holder["error"]
    return holder["result"]


def _terminate(process) -> None:
    process.terminate()
    process.join(timeout=3)
    if process.is_alive():
        process.kill()
        process.join()


def execute_isolated(target_func, arguments: dict, cancel_event) -> Any:
    """子进程隔离执行：易卡死工具专用，打断时操作系统级 terminate 物理掐断"""
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    p = ctx.Process(target=process_worker, args=(target_func, arguments, result_queue))
    p.start()

    started_at = time.monotonic()
    res = None
    while True:
        # 1. 优先响应打断信号（物理级掐断！）
        if cancel_event is not None and cancel_event.is_set():
            _terminate(p)
            return interrupted_result()

        # 2. 硬墙钟上限兜底
        if time.monotonic() - started_at > HARD_WALL_LIMIT_SECONDS:
            _terminate(p)
            return {
                "content": (
                    f"⚠️ 工具执行已超过 {HARD_WALL_LIMIT_SECONDS // 60} 分钟硬上限，已被系统强制终止。"
                    "如果是长时任务请改用 Bash + nohup/后台启动，并通过日志文件跟进结果。"
                ),
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "error",
                    "snip": "⏱️ 工具执行超时",
                },
            }

        # 3. 先取结果再查进程存活（避免：进程 put 完退出后 is_alive 变 False 导致结果丢失）
        try:
            res = result_queue.get(timeout=0.2)
            break
        except queue.Empty:
            if not p.is_alive():
                # 进程已退出：做最后一次排水（feeder 线程的数据可能滞后到达）
                try:
                    res = result_queue.get(timeout=2.0)
                    break
                except queue.Empty:
                    return {
                        "content": "⚠️ 工具子进程意外终止，未能返回结果。",
                        "metadata": {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "type": "error",
                            "snip": "💥 进程崩溃",
                        },
                    }

    p.join(timeout=3)
    if res["status"] == "success":
        return res["data"]
    raise Exception(res["error"])


def execute_tool(
    target_func,
    arguments: dict,
    *,
    cancel_event=None,
    isolated: bool = False,
) -> Any:
    """按隔离策略执行工具：子进程=可物理打断 / 进程内=轻量快速"""
    if isolated:
        return execute_isolated(target_func, arguments, cancel_event)
    return execute_inline(target_func, arguments, cancel_event)
