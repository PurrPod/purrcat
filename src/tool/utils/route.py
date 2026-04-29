import json
import os
import uuid
import time
import importlib
import traceback
import inspect
import asyncio
import base64
import mimetypes
from typing import Any


# 工具名到函数名的映射表（处理驼峰命名等特殊情况）
TOOL_FUNC_MAP = {
    "filesystem": "FileSystem",
    "bash": "Bash",
    "cron": "Cron",
    "mcp": "CallMCP",
    "memo": "Memo",
    "search": "Search",
    "fetch": "Fetch",
    "task": "Task"
}


def _safe_truncate(data: Any, max_len: int) -> str:
    """结构化安全省略策略：防止粗暴截断破坏 JSON 或格式闭合"""
    data_str = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
    if len(data_str) <= max_len:
        return data_str
    if isinstance(data, list):
        # 对列表进行二分法安全截断，保证结构完整
        left, right = 0, len(data)
        valid_slice = []
        while left < right:
            mid = (left + right + 1) // 2
            test_str = json.dumps(data[:mid], ensure_ascii=False)
            if len(test_str) <= max_len:
                valid_slice = data[:mid]
                left = mid
            else:
                right = mid - 1

        omitted_count = len(data) - len(valid_slice)
        if omitted_count > 0:
            valid_slice.append(f"...(已省略剩余 {omitted_count} 项，空间不足)")
        return json.dumps(valid_slice, ensure_ascii=False)
    # 对于长文本或无法切片的字典，退化为首尾保留文本截断
    preview_front = data_str[:max_len // 2]
    preview_back = data_str[-max_len // 2:]
    omitted = len(data_str) - max_len
    return f"{preview_front}\n\n... [中间 {omitted} 字符已折叠，防止撑爆上下文] ...\n\n{preview_back}"


def _handle_media_content(parsed_res: dict, tool_name: str) -> str:
    """
    处理多媒体内容：将图片、视频、音频、PDF 等保存到本地文件
    """
    content_data = parsed_res.get("content", {})
    
    if not isinstance(content_data, dict):
        return None
    
    media_type = content_data.get("type")
    if media_type not in ["image", "video", "audio", "pdf", "mcp_media", "media_url", "media_base64"]:
        return None
    
    buffer_dir = os.path.abspath("agent_vm/.buffer")
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
        
        # 保存完毕后，改写为纯文本消息
        sandbox_path = f"/agent_vm/.buffer/{filename}"
        media_desc = {
            "image": "🖼️ 图片",
            "video": "📹 视频",
            "audio": "🎵 音频",
            "pdf": "📄 PDF",
            "mcp_media": "📦 媒体",
            "media_url": "🔗 下载文件",
            "media_base64": "📦 Base64 文件"
        }.get(media_type, "📦 文件")
        
        parsed_res["type"] = "text"
        parsed_res["content"] = f"{media_desc}已成功保存至本地:\n" \
                               f"📂 宿主机路径: {filepath}\n" \
                               f"🐳 沙盒内路径: {sandbox_path}"
        
        return json.dumps(parsed_res, ensure_ascii=False)
    
    except Exception as e:
        print(f"⚠️ [多媒体处理异常] {e}")
        return None


def _execute_tool(target_func, arguments: dict) -> Any:
    """
    执行工具函数，支持同步和异步函数
    """
    # 兼容异步工具执行
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


def dispatch_tool(tool_name: str, arguments: dict, available_tokens: int = None) -> str:
    """
    核心路由枢纽：统一处理工具调用的路由和执行
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数
        available_tokens: 可用tokens数量（用于动态计算字数限制）
    
    Returns:
        格式化后的工具执行结果JSON字符串
    """
    result_content = ""
    
    try:
        # 获取函数名（优先使用映射表，否则使用首字母大写）
        func_name = TOOL_FUNC_MAP.get(tool_name.lower(), tool_name.capitalize())
        
        # 构建模块路径：tool.{tool_name}.{tool_name}
        module_path = f"src.tool.{tool_name}.{tool_name}"
        try:
            tool_module = importlib.import_module(module_path)
        except ImportError:
            # 尝试不带后缀的路径
            module_path = f"src.tool.{tool_name}"
            tool_module = importlib.import_module(module_path)
        
        # 获取工具函数
        if not hasattr(tool_module, func_name):
            raise AttributeError(f"工具模块 '{module_path}' 中未找到函数: {func_name}")
        
        target_func = getattr(tool_module, func_name)
        
        # 执行工具（支持同步和异步）
        result_content = _execute_tool(target_func, arguments)
        
        # 先检查是否为多媒体内容
        try:
            result_str = str(result_content)
            parsed_res = json.loads(result_str)
            
            # 处理多媒体内容
            media_result = _handle_media_content(parsed_res, tool_name)
            if media_result:
                result_content = media_result
                result_str = media_result
                parsed_res = json.loads(result_str)
        except json.JSONDecodeError:
            parsed_res = None
        
        # 字数限制拦截逻辑
        MAX_LEN = 6000  # 默认降级阈值
        if available_tokens is not None:
            dynamic_max_len = int((available_tokens - 500) * 1.5)
            MAX_LEN = max(500, dynamic_max_len)
        
        if result_content and isinstance(result_content, str):
            result_str = result_content
        else:
            result_str = str(result_content)
        
        try:
            parsed_res = json.loads(result_str)
            content_data = parsed_res.get("content", "")
            # 为了准确计算长度，将字典/列表格式的内容转为字符串
            actual_content_str = json.dumps(content_data, ensure_ascii=False) if isinstance(content_data, (dict, list)) else str(content_data)
        except json.JSONDecodeError:
            parsed_res = None
            content_data = result_str
            actual_content_str = result_str
        
        # 超标验证（load_skill 工具除外）
        if len(actual_content_str) > MAX_LEN and tool_name != "load_skill":
            # 按工具名称分类全量存储
            buffer_dir = os.path.abspath("agent_vm/.buffer")
            tool_dir = os.path.join(buffer_dir, tool_name)
            os.makedirs(tool_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            file_name = f"{timestamp}_{uuid.uuid4().hex[:4]}.txt"
            cache_path = os.path.join(tool_dir, file_name)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(actual_content_str)
            
            # 执行结构化截断
            truncated_str = _safe_truncate(content_data, MAX_LEN)
            warning_msg = (
                f"⚠️ [系统拦截] {tool_name} 输出总长 {len(actual_content_str)} 字符，超出当前安全余量阈值 {MAX_LEN}。完整结果已落盘：\n"
                f"📂 宿主机路径: {cache_path}\n"
                f"🐳 沙盒内路径: /agent_vm/.buffer/{tool_name}/{file_name}\n"
                f"如果你需要查看剩余的内容，请用 Bash (cat/grep) 或 filesystem 工具去上述缓存文件里阅读全量数据！\n"
                f"\n--- 结构化内容预览 ---\n"
                f"{truncated_str}"
            )
            
            # 安全回填内容
            if parsed_res and isinstance(parsed_res, dict):
                parsed_res["type"] = "warning"
                parsed_res["content"] = warning_msg
                result_content = json.dumps(parsed_res, ensure_ascii=False)
            else:
                from src.tool.utils.format import warning_response
                result_content = warning_response(warning_msg)
    
    except Exception as e:
        traceback.print_exc()
        from src.tool.utils.format import error_response
        result_content = error_response(f"❌ 工具 [{tool_name}] 调度/执行发生异常: {str(e)}")
    
    return str(result_content)