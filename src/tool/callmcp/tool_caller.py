"""MCP 工具调用模块 - 执行 MCP 工具调用"""

import asyncio
import base64
import os
import time
import uuid
from typing import Dict, List

from src.tool.callmcp import _shared, mcp_apps
from src.tool.callmcp.exceptions import (
    ServerConnectionError,
    ServerNotFoundError,
    ToolExecutionError,
)
from src.tool.callmcp.session_manager import _run_sync, load_configs, mcp_manager
from src.utils.config import BUFFER_DIR


def _tool_ui_resource(server_name: str, tool_name: str) -> str | None:
    """从 Schema 缓存里取该工具的 UI 资源地址（未声明 UI 则返回 None）。"""
    from src.tool.callmcp.schema_manager import load_cached_schemas

    for schema in load_cached_schemas():
        if schema.get("server") != server_name:
            continue
        if schema.get("function", {}).get("name") != tool_name:
            continue
        return mcp_apps.ui_resource_uri(schema.get("_meta"))
    return None


async def _read_ui_html(session, uri: str) -> str | None:
    """读取 UI 资源并返回 HTML 文本；MIME 不是 HTML 时忽略。"""
    result = await session.read_resource(uri)
    for content in getattr(result, "contents", []) or []:
        mime = getattr(content, "mimeType", None)
        if not mcp_apps.is_mcp_app_mime(mime):
            continue
        text = getattr(content, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        blob = getattr(content, "blob", None)
        if isinstance(blob, str) and blob:
            return base64.b64decode(blob).decode("utf-8", errors="replace")
    return None


def _result_payload(result) -> dict:
    """截取 App 需要的调用结果字段（空值不写入，避免校验失败）。"""
    dumped = result.model_dump(mode="json", exclude_none=True)
    payload = {"content": dumped.get("content", [])}
    if dumped.get("structuredContent") is not None:
        payload["structuredContent"] = dumped["structuredContent"]
    if dumped.get("meta") is not None:
        payload["_meta"] = dumped["meta"]
    return payload


async def _invoke_tool_async(
    server_name: str, tool_name: str, arguments: dict, tool_call_id: str | None
) -> tuple[List[str], bool]:
    """异步调用 MCP 工具，返回 (文本输出, 是否已落盘 MCP App)。"""
    servers = load_configs()
    if server_name not in servers:
        raise ServerNotFoundError(server_name)

    config = servers[server_name]

    try:
        session = await mcp_manager.get_session(server_name, config)
        # ⏱️ callmcp 已改为进程内执行以维持 MCP 长连接（不能靠杀子进程防卡死），
        # 用 wait_for 超时兜底；超时会走下方异常分支清理并重建会话
        call_timeout = config.get("call_timeout", 300)
        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments), timeout=call_timeout
        )

        if server_name in mcp_manager.sessions:
            mcp_manager.sessions[server_name]["last_active"] = time.time()

        if result.isError:
            error_details = "\n".join(
                [c.text for c in result.content if c.type == "text"]
            )
            raise ToolExecutionError(tool_name, error_details)

        output = []
        for content in result.content:
            if content.type == "text":
                output.append(content.text)
            elif content.type == "image" or hasattr(content, "data"):
                try:
                    raw_data, ext = _shared.decode_image_content(content)

                    save_dir = os.path.join(BUFFER_DIR, "mcp_media")
                    os.makedirs(save_dir, exist_ok=True)

                    file_path = os.path.join(
                        save_dir, f"mcp_img_{uuid.uuid4().hex[:8]}.{ext}"
                    )
                    with open(file_path, "wb") as f:
                        f.write(raw_data)

                    output.append(f"🖼️ [截图/图片已生成并保存至宿主机]: {file_path}")
                except Exception as e:
                    output.append(f"❌ [{content.type} 类型解析失败: {str(e)}]")
            else:
                output.append(
                    f"[{content.type} 类型内容]: {str(getattr(content, '__dict__', content))}"
                )

        app_saved = False
        resource_uri = _tool_ui_resource(server_name, tool_name)
        if resource_uri and mcp_apps.is_legal_app_id(tool_call_id):
            try:
                html = await _read_ui_html(session, resource_uri)
                if html:
                    app_saved = mcp_apps.save_app(
                        tool_call_id,
                        {
                            "server": server_name,
                            "tool": tool_name,
                            "uri": resource_uri,
                            "arguments": arguments,
                            "result": _result_payload(result),
                        },
                        html,
                    )
            except Exception as e:
                print(f"⚠️ [MCP App] 读取 UI 资源失败 {resource_uri}: {e}")

        if not app_saved and mcp_apps.is_legal_app_id(tool_call_id):
            structured = getattr(result, "structuredContent", None)
            if structured is None:
                texts = [c.text for c in result.content if c.type == "text"]
                structured = (
                    mcp_apps.extract_json_text(texts[0]) if len(texts) == 1 else None
                )
            if structured is not None:
                mcp_apps.save_result(
                    tool_call_id,
                    {
                        "server": server_name,
                        "tool": tool_name,
                        "structuredContent": structured,
                    },
                )

        return output, app_saved

    except RuntimeError as re:
        raise re
    except Exception as e:
        print(f"⚠️ [MCP 异常] 检测到进程崩溃或连接断开: {e}，正在强制清理缓存池...")
        await mcp_manager._close_session(server_name)
        raise ServerConnectionError(server_name, str(e))


async def _call_tool_async(
    server_name: str, tool_name: str, arguments: dict
) -> List[str]:
    """异步调用 MCP 工具（无 App 落盘）。"""
    output, _ = await _invoke_tool_async(server_name, tool_name, arguments, None)
    return output


async def _list_tools_async(server_name: str = None) -> List[Dict]:
    """异步获取工具列表"""
    servers = load_configs()
    tools_index = []

    target_servers = (
        [(server_name, servers[server_name])] if server_name else servers.items()
    )

    for name, config in target_servers:
        try:
            session = await mcp_manager.get_session(name, config)
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                tools_index.append(
                    {
                        "server": name,
                        "name": tool.name,
                        "description": tool.description or "无描述",
                    }
                )
        except Exception as e:
            print(f"❌ [MCP] 获取 {name} 工具列表失败: {e}")

    return tools_index


def call_mcp_tool(server_name: str, tool_name: str, arguments: dict) -> List[str]:
    """同步调用 MCP 工具"""
    return _run_sync(_call_tool_async, server_name, tool_name, arguments)


def call_mcp_tool_with_ui(
    server_name: str, tool_name: str, arguments: dict, tool_call_id: str | None = None
) -> tuple[List[str], bool]:
    """同步调用 MCP 工具，工具声明了 UI 资源时按 tool_call_id 落盘 App。"""
    return _run_sync(
        _invoke_tool_async, server_name, tool_name, arguments, tool_call_id
    )


def list_mcp_tools(server_name: str = None) -> List[Dict]:
    """同步获取工具列表"""
    return _run_sync(_list_tools_async, server_name)
