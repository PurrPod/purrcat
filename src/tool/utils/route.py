import asyncio
import base64
import importlib
import inspect
import json
import mimetypes
import os
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
    if media_type not in ["image", "video", "audio", "pdf", "mcp_media", "media_url", "media_base64"]:
        return content_data

    buffer_dir = BUFFER_DIR
    os.makedirs(buffer_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    marker_id = uuid.uuid4().hex[:8]

    try:
        if media_type == "media_url":
            import urllib.request
            url = content_data["url"]
            ext = content_data.get("ext", ".bin")
            filename = f"{tool_name}_{timestamp}_{marker_id}{ext}"
            filepath = os.path.join(buffer_dir, filename)
            urllib.request.urlretrieve(url, filepath)

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
            "image": "🖼️ 图片", "video": "📹 视频", "audio": "🎵 音频",
            "pdf": "📄 PDF", "mcp_media": "📦 媒体", "media_url": "🔗 下载文件",
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


def _execute_tool(target_func, arguments: dict) -> Any:
    """执行工具函数，支持同步和异步"""
    if inspect.iscoroutinefunction(target_func):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            result = asyncio.get_event_loop().run_until_complete(target_func(**arguments))
        else:
            result = asyncio.run(target_func(**arguments))
    else:
        result = target_func(**arguments)

    return result


def dispatch_tool(tool_name: str, arguments: dict, available_tokens: int = None):
    """
    核心路由枢纽：纯净的数据流处理
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
        result_obj = _execute_tool(target_func, arguments)

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
                "snip": ""
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
            content_data = yaml.dump(content_data, allow_unicode=True, default_flow_style=False)
            content_data = f"【系统格式化输出】\n{content_data}"

        # 7. 最终封包组装返回给 LLM （只保留 content 和 metadata）
        final_response = {
            "content": str(content_data),
            "metadata": metadata
        }
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
                "snip": "❌ 执行异常"
            }
        }
        return json.dumps(final_err_res, ensure_ascii=False)
