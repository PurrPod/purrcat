import asyncio
import base64
import importlib
import inspect
import json
import mimetypes
import multiprocessing
import os
import queue
import time
import traceback
import uuid
from typing import Any

from src.utils.config import BUFFER_DIR

# 工具名到函数名的映射表
TOOL_FUNC_MAP = {
    "filesystem": "FileSystem",
    "bash": "Bash",
    "brainstorm": "BrainStorm",
    "computeruse": "ComputerUse",
    "cron": "Cron",
    "callmcp": "CallMCP",
    "memo": "Memo",
    "request": "Request",
    "search": "Search",
    "fetch": "Fetch",
    "task": "Task",
    "kernelupgrade": "KernelUpgrade",  # 🌟 新增注册
}

# 🌟 进程隔离名单：只有这些「易卡死」的工具才丢进子进程执行（可被物理级 terminate）
# 其余工具（memo/filesystem/cron/task/brainstorm/kernelupgrade）持有进程内状态
# （如 brainstorm/task 会 lazy import AgentManager），子进程化会出灾难性后果，保持进程内执行
PROCESS_ISOLATED_TOOLS = {
    "bash",  # 长时命令 / 死循环
    "request",  # 网络请求
    "fetch",  # 网络抓取
    "search",  # 向量检索（含嵌入计算）
    "callmcp",  # 外部 MCP Server 调用
    "computeruse",  # UI 自动化
}


def _safe_truncate(data: Any, max_len: int) -> str:
    """结构化安全省略策略：基于纯净 content 直接格式化"""
    data_str = (
        json.dumps(data, ensure_ascii=False, indent=2)
        if isinstance(data, (dict, list))
        else str(data)
    )

    if len(data_str) <= max_len:
        return data_str

    # 仅保留前端
    preview_front = data_str[:max_len]
    omitted = len(data_str) - max_len
    return f"{preview_front}\n\n... [后续 {omitted} 字符已被截断，请使用 Bash 工具读取落盘的缓存文件] ..."


def _handle_media_content(content_data: Any, tool_name: str) -> Any:
    """处理多媒体内容，直接对原生 content_data 操作"""
    if not isinstance(content_data, dict):
        return content_data

    media_type = content_data.get("type")
    if media_type not in [
        "image",
        "video",
        "audio",
        "pdf",
        "mcp_media",
        "media_url",
        "media_base64",
    ]:
        return content_data

    buffer_dir = BUFFER_DIR
    os.makedirs(buffer_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    marker_id = uuid.uuid4().hex[:8]

    try:
        if media_type == "media_url":
            import shutil
            import urllib.request

            url = content_data["url"]
            ext = content_data.get("ext", ".bin")
            filename = f"{tool_name}_{timestamp}_{marker_id}{ext}"
            filepath = os.path.join(buffer_dir, filename)
            # 🌟 带超时的流式下载（urlretrieve 无超时，卡死时同样无法打断）
            with (
                urllib.request.urlopen(url, timeout=60) as r,
                open(filepath, "wb") as f,
            ):
                shutil.copyfileobj(r, f)

        elif media_type in ["image", "video", "audio", "pdf", "mcp_media"]:
            data = content_data["data"]
            ext = content_data.get("ext", ".bin")
            if media_type == "mcp_media":
                mime_type = content_data.get("mimeType", ".bin")
                if mime_type.startswith("image/"):
                    ext = ".png"
                else:
                    ext = mimetypes.guess_extension(mime_type) or ".bin"
            filename = f"{tool_name}_{timestamp}_{marker_id}{ext}"
            filepath = os.path.join(buffer_dir, filename)
            binary_data = base64.b64decode(data)
            with open(filepath, "wb") as f:
                f.write(binary_data)

        elif media_type == "media_base64":
            data = content_data["data"]
            ext = content_data.get("ext", ".bin")
            filename = f"{tool_name}_{timestamp}_{marker_id}{ext}"
            filepath = os.path.join(buffer_dir, filename)
            binary_data = base64.b64decode(data)
            with open(filepath, "wb") as f:
                f.write(binary_data)

        sandbox_path = f"/agent_vm/.buffer/{filename}"
        media_desc = {
            "image": "🖼️ 图片",
            "video": "📹 视频",
            "audio": "🎵 音频",
            "pdf": "📄 PDF",
            "mcp_media": "📦 媒体",
            "media_url": "🔗 下载文件",
            "media_base64": "📦 Base64 文件",
        }.get(media_type, "📦 文件")

        # 媒体处理成功后，将原本笨重的二进制字典退化成路径文本提示
        return (
            f"{media_desc}已成功保存至本地:\n"
            f"📂 宿主机路径: {filepath}\n"
            f"🐳 沙盒内路径: {sandbox_path}"
        )

    except Exception as e:
        print(f"⚠️ [多媒体处理异常] {e}")
        return content_data


def _run_func_sync(target_func, arguments: dict) -> Any:
    """执行工具函数，支持同步和异步（工作线程/子进程内运行，无事件循环）"""
    if inspect.iscoroutinefunction(target_func):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio

            nest_asyncio.apply()
            result = asyncio.get_event_loop().run_until_complete(
                target_func(**arguments)
            )
        else:
            result = asyncio.run(target_func(**arguments))
    else:
        result = target_func(**arguments)

    return result


def _process_worker(target_func, kwargs, result_queue):
    """子进程入口：执行工具并把结果/异常放回队列（模块级函数，可被 pickle）"""
    try:
        res = _run_func_sync(target_func, kwargs)
        result_queue.put({"status": "success", "data": res})
    except BaseException as e:
        result_queue.put({"status": "error", "error": f"{type(e).__name__}: {e}"})


def _interrupted_result() -> dict:
    """伪造的打断结果：返回给 LLM，告知执行已被人类打断"""
    return {
        "content": "【系统强制打断】工具执行已被人类打断，请停下你的工作接收新指令。",
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "warning",
            "snip": "⚡ 执行被人类打断",
        },
    }


def _execute_tool_inline(target_func, arguments: dict, cancel_event) -> Any:
    """进程内执行（守护线程 + 轮询）：轻量工具用，打断时放弃线程直接返回伪造结果"""
    import threading

    holder = {}

    def _worker():
        try:
            holder["result"] = _run_func_sync(target_func, arguments)
        except BaseException as e:
            holder["error"] = e

    t = threading.Thread(target=_worker, daemon=True, name="ToolInlineWorker")
    t.start()
    while True:
        if "result" in holder or "error" in holder:
            break
        if cancel_event is not None and cancel_event.is_set():
            # 放弃该守护线程（轻量工具毫秒级完成，极小概率泄漏），立刻让路
            return _interrupted_result()
        t.join(timeout=0.2)
    if "error" in holder:
        raise holder["error"]
    return holder["result"]


def _execute_tool_isolated(target_func, arguments: dict, cancel_event) -> Any:
    """子进程隔离执行：易卡死工具专用，打断时操作系统级 terminate 物理掐断"""
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    p = ctx.Process(target=_process_worker, args=(target_func, arguments, result_queue))
    p.start()

    # ⚡ 墙钟总超时（兜底卡死工具）：超过此时间即使没人点「中断」也强制掐断
    # 注意：这个超时需要大于各工具自身的 timeout，避免误杀正常长请求；
    # 目前按 12 分钟取，足以覆盖 60s fetch / 2h bash 等常见场景的典型请求，
    # 但对真正的长时 bash 会被误杀；为防止误杀，仅对网络类工具生效。
    # 这里保持「无限」，但会在下面的 drain 循环中通过开始时间做保守兜底（30 分钟硬上限）。
    started_at = time.monotonic()
    HARD_WALL_LIMIT = 30 * 60  # 30 分钟硬上限：任何子进程工具都不允许无限挂起

    res = None
    while True:
        # 1. 优先响应打断信号（物理级掐断！）
        if cancel_event is not None and cancel_event.is_set():
            p.terminate()
            p.join(timeout=3)
            if p.is_alive():
                p.kill()
                p.join()
            return _interrupted_result()

        # 1.5 硬墙钟上限兜底
        if time.monotonic() - started_at > HARD_WALL_LIMIT:
            p.terminate()
            p.join(timeout=3)
            if p.is_alive():
                p.kill()
                p.join()
            return {
                "content": (
                    f"⚠️ 工具执行已超过 {HARD_WALL_LIMIT // 60} 分钟硬上限，已被系统强制终止。"
                    "如果是长时任务请改用 Bash + nohup/后台启动，并通过日志文件跟进结果。"
                ),
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "error",
                    "snip": "⏱️ 工具执行超时",
                },
            }

        # 2. 先取结果再查进程存活（避免：进程 put 完退出后 is_alive 变 False 导致结果丢失）
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


def _execute_tool(
    target_func, arguments: dict, cancel_event=None, tool_name: str = ""
) -> Any:
    """执行工具函数：按隔离名单分流（子进程=可物理打断 / 进程内=轻量快速）"""
    if tool_name.lower() in PROCESS_ISOLATED_TOOLS:
        return _execute_tool_isolated(target_func, arguments, cancel_event)
    return _execute_tool_inline(target_func, arguments, cancel_event)


def dispatch_tool(
    tool_name: str, arguments: dict, available_tokens: int = None, cancel_event=None
):
    """
    核心路由枢纽：纯净的数据流处理
    cancel_event: threading.Event，被 set 时物理掐断正在执行的工具并返回伪造打断结果
    """
    try:
        tool_name_lower = tool_name.lower()
        func_name = TOOL_FUNC_MAP.get(tool_name_lower, tool_name.capitalize())

        module_path = f"src.tool.{tool_name_lower}.{tool_name_lower}"
        try:
            tool_module = importlib.import_module(module_path)
        except ImportError:
            module_path = f"src.tool.{tool_name_lower}"
            tool_module = importlib.import_module(module_path)

        if not hasattr(tool_module, func_name):
            raise AttributeError(f"工具模块 '{module_path}' 中未找到函数: {func_name}")

        target_func = getattr(tool_module, func_name)

        # 1. 获得执行结果 (新版统一格式 {"content": ..., "metadata": {...}})
        result_obj = _execute_tool(
            target_func, arguments, cancel_event=cancel_event, tool_name=tool_name_lower
        )

        # 2. 优雅解包数据与元数据
        if isinstance(result_obj, dict) and "metadata" in result_obj:
            content_data = result_obj.get("content", "")
            metadata = result_obj.get("metadata", {})
        else:
            # 兼容未改造完毕的旧工具
            content_data = result_obj
            metadata = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "text",
                "snip": "",
            }

        # 3. 如果是多媒体文件字典，这里将其退化成纯文本的路径提示
        content_data = _handle_media_content(content_data, tool_name_lower)

        # 4. 生成用于判断长度与落盘的纯净字符串
        if isinstance(content_data, (dict, list)):
            actual_content_str = json.dumps(content_data, ensure_ascii=False, indent=2)
        else:
            actual_content_str = str(content_data)

        # 5. 长度拦截判断
        MAX_LEN = 5000
        if available_tokens is not None:
            dynamic_max_len = int((available_tokens - 500) * 1.5)
            MAX_LEN = min(5000, max(500, dynamic_max_len))

        is_fetch_skill = (
            tool_name_lower == "fetch"
            and arguments.get("source", "").lower() == "skill"
        )

        if len(actual_content_str) > MAX_LEN and not is_fetch_skill:
            # 📂 纯净落盘：100% 只保存数据本体，无协议头污染
            buffer_dir = BUFFER_DIR
            tool_dir = os.path.join(buffer_dir, tool_name_lower)
            os.makedirs(tool_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            file_name = f"{timestamp}_{uuid.uuid4().hex[:4]}.txt"
            cache_path = os.path.join(tool_dir, file_name)

            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(actual_content_str)

            # 🛠️ 覆盖更新 Context 与 Metadata
            truncated_str = _safe_truncate(content_data, MAX_LEN)
            warning_msg = (
                f"⚠️ [系统拦截] {tool_name} 输出总长 {len(actual_content_str)} 字符，超出当前安全余量阈值。完整结果已落盘：\n"
                f"🐳 沙盒内路径: /agent_vm/.buffer/{tool_name_lower}/{file_name}\n"
                f"如果你需要查看剩余的内容，请务必使用 Bash (cat/grep/sed/tail) 工具去上述缓存文件里分批阅读！\n"
                f"\n--- 内容预览 (前 {MAX_LEN} 字符) ---\n"
                f"{truncated_str}"
            )

            content_data = warning_msg
            metadata["type"] = "warning"
            metadata["snip"] = "字数超长已被截断并落盘"

        # 6. 强制将遗漏的 dict/list 转换为自然语言纯文本（防 JSON 解析）
        if isinstance(content_data, (dict, list)):
            import yaml

            content_data = yaml.dump(
                content_data, allow_unicode=True, default_flow_style=False
            )
            content_data = f"【系统格式化输出】\n{content_data}"

        # 7. 最终封包组装返回给 LLM （只保留 content 和 metadata）
        final_response = {"content": str(content_data), "metadata": metadata}
        return json.dumps(final_response, ensure_ascii=False)

    except Exception as e:
        traceback.print_exc()
        # 异常兜底构造
        err_msg = f"❌ 工具 [{tool_name}] 调度/执行发生异常: {str(e)}"
        final_err_res = {
            "content": err_msg,
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "error",
                "snip": "❌ 执行异常",
            },
        }
        return json.dumps(final_err_res, ensure_ascii=False)
