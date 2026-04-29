"""MCP 工具调用模块 - 执行 MCP 工具调用"""

import base64
import json
import os
import uuid
from typing import Any, List, Dict

from src.tool.mcp.session_manager import mcp_manager, load_configs, _run_sync
from src.tool.mcp.exceptions import (
    ServerNotFoundError,
    ServerConnectionError,
    ToolExecutionError
)


async def _call_tool_async(server_name: str, tool_name: str, arguments: dict) -> List[str]:
    """异步调用 MCP 工具"""
    servers = load_configs()
    if server_name not in servers:
        raise ServerNotFoundError(server_name)
    
    config = servers[server_name]

    try:
        session = await mcp_manager.get_session(server_name, config)
        result = await session.call_tool(tool_name, arguments)

        if server_name in mcp_manager.sessions:
            mcp_manager.sessions[server_name]["last_active"] = time.time()

        if result.isError:
            error_details = "\n".join([c.text for c in result.content if c.type == "text"])
            raise ToolExecutionError(tool_name, error_details)

        output = []
        for content in result.content:
            if content.type == "text":
                output.append(content.text)
            elif content.type == "image" or hasattr(content, "data"):
                try:
                    mime_type = getattr(content, "mimeType", "image/png")
                    b64_data = content.data
                    if "," in b64_data and b64_data.startswith("data:"):
                        b64_data = b64_data.split(",", 1)[1]
                    
                    ext = mime_type.split('/')[-1] if '/' in mime_type else 'png'
                    if ext == 'jpeg':
                        ext = 'jpg'
                    
                    save_dir = os.path.join("agent_vm", ".buffer", "mcp_media")
                    os.makedirs(save_dir, exist_ok=True)
                    
                    file_path = os.path.join(save_dir, f"mcp_img_{uuid.uuid4().hex[:8]}.{ext}")
                    with open(file_path, "wb") as f:
                        f.write(base64.b64decode(b64_data))
                    
                    output.append(f"🖼️ [截图/图片已生成并保存至宿主机]: {file_path}")
                except Exception as e:
                    output.append(f"❌ [{content.type} 类型解析失败: {str(e)}]")
            else:
                output.append(f"[{content.type} 类型内容]: {str(getattr(content, '__dict__', content))}")

        return output

    except RuntimeError as re:
        raise re
    except Exception as e:
        print(f"⚠️ [MCP 异常] 检测到进程崩溃或连接断开: {e}，正在强制清理缓存池...")
        await mcp_manager._close_session(server_name)
        raise ServerConnectionError(server_name, str(e))


async def _list_tools_async(server_name: str = None) -> List[Dict]:
    """异步获取工具列表"""
    servers = load_configs()
    tools_index = []
    
    target_servers = [(server_name, servers[server_name])] if server_name else servers.items()
    
    for name, config in target_servers:
        try:
            session = await mcp_manager.get_session(name, config)
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                tools_index.append({
                    "server": name,
                    "name": tool.name,
                    "description": tool.description or "无描述"
                })
        except Exception as e:
            print(f"❌ [MCP] 获取 {name} 工具列表失败: {e}")
    
    return tools_index


def call_mcp_tool(server_name: str, tool_name: str, arguments: dict) -> List[str]:
    """同步调用 MCP 工具"""
    return _run_sync(_call_tool_async, server_name, tool_name, arguments)


def list_mcp_tools(server_name: str = None) -> List[Dict]:
    """同步获取工具列表"""
    return _run_sync(_list_tools_async, server_name)