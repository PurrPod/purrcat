import json
import os
import traceback
import uuid
import time
from typing import Any
from src.utils.config import TOOL_INDEX_FILE


def _format_response(msg_type: str, content: Any) -> str:
    """确保内部所有报错调度也符合统一格式"""
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def parse_tool(tool_name: str, arguments: dict, route: str = None, plugin: str = None) -> tuple[str, list]:
    """
    核心枢纽：统一处理工具调用的路由和执行。
    【唯一异常拦截口】所有底层异常都在此被统一处理和格式化
    【全局字数检测】超长输出自动落盘缓存，防止大模型被撑爆
    """
    new_schema_info = None
    result_content = ""
    try:
        # 1. 尝试将请求路由给 base_tool
        from src.plugins.route.base_tool import BASE_TOOL_NAMES, call_base_tool
        if tool_name in BASE_TOOL_NAMES or tool_name == "close_shell":
            result_content, new_schema_info = call_base_tool(tool_name, arguments)

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
        MAX_LEN = 3000  # 阈值可以根据需要调大，比如 5000
        result_str = str(result_content)
        try:
            parsed_res = json.loads(result_str)
            content_data = parsed_res.get("content", "")
            # 为了准确计算长度，将字典格式的内容转为字符串（比如 execute_command 返回的是 dict）
            actual_content_str = json.dumps(content_data, ensure_ascii=False) if isinstance(content_data, dict) else str(content_data)
        except json.JSONDecodeError:
            parsed_res = None
            actual_content_str = result_str

        if len(actual_content_str) > MAX_LEN:
            cache_dir = os.path.abspath("data/cache/tool_outputs")
            os.makedirs(cache_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            file_name = f"{tool_name}_{timestamp}_{uuid.uuid4().hex[:4]}.txt"
            cache_path = os.path.join(cache_dir, file_name)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(actual_content_str)
            preview_front = actual_content_str[:MAX_LEN // 2]
            preview_back = actual_content_str[-MAX_LEN // 2:]
            warning_msg = (
                f"⚠️ [系统拦截] {tool_name} 输出总长 {len(actual_content_str)} 字符，超出阈值 {MAX_LEN}。完整结果已落盘：\n"
                f"📂 宿主机路径: {cache_path}\n"
                f"🐳 沙盒内路径: /agent_vm/cache/tool_outputs/{file_name} (假设做了目录挂载映射)\n"
                f"\n--- 内容预览 (首尾各截取部分) ---\n"
                f"{preview_front}\n\n... [中间 {len(actual_content_str) - MAX_LEN} 字符已折叠] ...\n\n{preview_back}"
            )
            
            # 安全回填内容
            if parsed_res and isinstance(parsed_res, dict):
                parsed_res["type"] = "warning" 
                parsed_res["content"] = warning_msg
                result_content = json.dumps(parsed_res, ensure_ascii=False)
            else:
                result_content = _format_response("warning", warning_msg)
    except Exception as e:
        # 【黑洞异常处理】底层所有异常都冒泡到这里被统一捕获
        traceback.print_exc()  # 打印完整报错栈便于本地开发调试
        result_content = _format_response("error", f"❌ 工具 [{tool_name}] 调度/执行发生异常: {str(e)}")
    return str(result_content), new_schema_info