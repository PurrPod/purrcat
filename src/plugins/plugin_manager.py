import json
import os
import traceback
import uuid
import time
import base64
import mimetypes
from typing import Any
from src.utils.config import TOOL_INDEX_FILE


def _format_response(msg_type: str, content: Any) -> str:
    """确保内部所有报错调度也符合统一格式"""
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


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

def parse_tool(tool_name: str, arguments: dict, route: str = None, plugin: str = None, available_tokens: int = None) -> str:
    """
    核心枢纽：统一处理工具调用的路由和执行。
    【唯一异常拦截口】所有底层异常都在此被统一处理和格式化
    【全局字数检测】支持动态可用 Tokens 估算，超长输出自动落盘缓存加结构化省略
    """
    result_content = ""
    try:
        # 1. 尝试将请求路由给 base_tool
        from src.plugins.route.base_tool import BASE_TOOL_NAMES, call_base_tool
        if tool_name in BASE_TOOL_NAMES or tool_name == "close_shell":
            result_content = call_base_tool(tool_name, arguments)
        # 2. 如果不是 base_tool，走具体的路由和 Agent 逻辑
        else:
            from src.plugins.route.agent_tool import AGENT_TOOL_FUNCTIONS
            if tool_name in AGENT_TOOL_FUNCTIONS:
                from src.plugins.route.agent_tool import call_agent_tool
                result_content = call_agent_tool(tool_name, arguments)
            else:
                # 动态探活寻找正确的 Route 与 Plugin
                if not route or not plugin:
                    if os.path.exists(TOOL_INDEX_FILE):
                        with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                tool_info = json.loads(line)
                                if tool_info["func"] == tool_name:
                                    route = tool_info["route"]
                                    plugin = tool_info["plugin"]
                                    break
                # 路由分发
                if route == "local":
                    from src.plugins.route.local_tool import call_local_tool
                    result_content = call_local_tool(plugin, tool_name, arguments)
                elif route == "mcp":
                    from src.plugins.route.mcp_tool import call_mcp_tool
                    result_content = call_mcp_tool(plugin, tool_name, arguments)
                else:
                    raise ValueError(f"❌ 未找到 {tool_name} 的底层路由映射。请确认它是否通过 fetch_tool 正常加载。")
        MAX_LEN = 6000  # 默认降级阈值
        if available_tokens is not None:
            dynamic_max_len = int((available_tokens - 500) * 1.5)
            MAX_LEN = max(500, dynamic_max_len)
        result_str = str(result_content)
        try:
            parsed_res = json.loads(result_str)
            content_data = parsed_res.get("content", "")
            # 检查是否为多媒体类型，需要在此处执行文件保存
            if isinstance(content_data, dict) and content_data.get("type") in ["image", "video", "audio", "pdf", "mcp_media", "media_url", "media_base64"]:
                media_type = content_data["type"]
                buffer_dir = os.path.abspath("agent_vm/.buffer")
                os.makedirs(buffer_dir, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                marker_id = uuid.uuid4().hex[:8]

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
                        ext = content_data.get("mimeType", ".bin")
                        if ext.startswith("image/"):
                            ext = ".png"
                        else:
                            ext = mimetypes.guess_extension(ext) or ".bin"
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

                # 保存完毕后，改写为纯文本
                parsed_res["type"] = "text"
                parsed_res["content"] = f"🖼️ 文件已成功保存至本地: {filepath}"
                result_content = json.dumps(parsed_res, ensure_ascii=False)
                result_str = result_content
                parsed_res = json.loads(result_str)
                content_data = parsed_res.get("content", "")

            # 为了准确计算长度，将字典/列表格式的内容转为字符串
            actual_content_str = json.dumps(content_data, ensure_ascii=False) if isinstance(content_data, (dict, list)) else str(content_data)
        except json.JSONDecodeError:
            parsed_res = None
            content_data = result_str
            actual_content_str = result_str
        # 超标验证
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
                f"如果你需要查看剩余的内容，请用 execute_command (cat/grep) 或 filesystem 工具去上述缓存文件里阅读全量数据！\n"
                f"\n--- 结构化内容预览 ---\n"
                f"{truncated_str}"
            )

            # 安全回填内容
            if parsed_res and isinstance(parsed_res, dict):
                parsed_res["type"] = "warning"
                parsed_res["content"] = warning_msg
                result_content = json.dumps(parsed_res, ensure_ascii=False)
            else:
                result_content = _format_response("warning", warning_msg)
    except Exception as e:
        traceback.print_exc()
        result_content = _format_response("error", f"❌ 工具 [{tool_name}] 调度/执行发生异常: {str(e)}")
    return str(result_content)