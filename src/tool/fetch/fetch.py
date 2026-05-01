import json
import os
import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.utils.config import SRC_DIR
from .exceptions import SkillNotFoundError, MCPServerNotFoundError, MCPToolNotFoundError, WebNetworkError
from .skill_fetch import load_skill
from .mcp_fetch import fetch_mcp_tools
from .web_content_fetch import web_content_fetch


def Fetch(source: str, name: str = None, serve_name: str = None, url: str = None, tool_names: list = None, **kwargs) -> str:
    try:
        valid_sources = ["skill", "mcp", "web", "harness", "todo"]
        source = source.strip().lower() if source else ""
        if source not in valid_sources:
            return error_response(f"source 必须是以下之一: {', '.join(valid_sources)}", "")

        result = None
        error = None

        if source == "skill":
            name = name or kwargs.get("name") or kwargs.get("skill_name")
            if not name:
                return error_response("获取 skill 缺少必要参数 name", "")
            result, error = load_skill(name)

        elif source == "mcp":
            serve_name = serve_name or kwargs.get("serve_name") or kwargs.get("server_name")
            tool_names = tool_names or kwargs.get("tool_names")
            if not tool_names and "tool_name" in kwargs:
                tool_names = [kwargs.get("tool_name")]

            if not serve_name:
                from src.tool.callmcp.session_manager import load_configs
                configs = load_configs()
                mcp_list = list(configs.keys())
                msg = "使用 Fetch(source='mcp', server_name='xxx') 获取工具详情"
                return text_response({
                    "configured_servers": mcp_list,
                    "message": msg
                }, f"📋 {len(mcp_list)}个MCP")

            result, error = fetch_mcp_tools(serve_name, tool_names)

        elif source == "web":
            url = url or kwargs.get("url") or kwargs.get("web_url")
            if not url:
                return error_response("获取 web 缺少必要参数 url", "")
            result, error = web_content_fetch(url)

        if error:
            return warning_response(error, f"⚠️ {source.upper()} 获取失败")

        if source == "skill":
            return text_response({
                "name": result["name"],
                "description": result["description"],
                "content": result["content"],
                "directory": result["directory"]
            }, f"📖 Skill [{name}]")

        elif source == "mcp":
            if not result:
                return text_response({
                    "server_name": serve_name,
                    "tool_names": tool_names,
                    "schemas": [],
                    "message": "暂无工具 Schema"
                }, "📭 暂无Schema")

            res_messages = []
            res_messages.append(f"成功找到 MCP Server '{serve_name}' 的工具信息。")
            res_messages.append("--- 工具 Schema ---")
            for schema in result:
                res_messages.append(json.dumps(schema["function"], ensure_ascii=False))
            res_messages.append("-----")
            res_messages.append("请使用 `CallMCP` 调用这些工具。")

            if tool_names:
                res_messages.append("如需更多工具，不传 tool_names 即可列出全部。")

            return text_response({
                "server_name": serve_name,
                "tool_names": [s["function"]["name"] for s in result],
                "schemas": result,
                "message": "\n".join(res_messages)
            }, f"🔧 {serve_name} | {len(result)}个工具")

        elif source == "harness":
            harness_path = os.path.join(SRC_DIR, "agent", "core", "HARNESS.md")
            if os.path.exists(harness_path):
                with open(harness_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return text_response({"content": content}, "📜 HARNESS")
            return error_response("未找到 HARNESS.md", "❌ 文件不存在")

        elif source == "todo":
            todo_path = os.path.join(SRC_DIR, "agent", "core", "TODO.md")
            if os.path.exists(todo_path):
                with open(todo_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    lines = content.split('\n')
                    return text_response({"content": content}, f"📝 {len(lines)}项")
            return text_response({"content": ""}, "📝 无待办")

        elif source == "web":
            content_len = len(result.get('content', ''))
            md = f"# {result['title']}\n\n**URL:** {result['url']}\n**类型:** {result['content_type']}\n---\n\n{result.get('content', '')[:2000]}"
            return text_response({
                "url": result["url"],
                "title": result["title"],
                "content_type": result["content_type"],
                "content": result["content"],
                "markdown": md
            }, f"🌐 {content_len}字符")

    except MCPServerNotFoundError as e:
        servers_str = ", ".join(e.available_servers) if e.available_servers else "无可用"
        return error_response(
            f"无法找到 MCP 服务器 '{e.serve_name}'。当前可用: [{servers_str}]",
            "❌ 服务器未找到"
        )
    except MCPToolNotFoundError as e:
        tools_str = ", ".join(e.available_tools) if e.available_tools else "无"
        return error_response(
            f"在 '{e.serve_name}' 中找不到工具 '{e.tool_name}'。现有工具: [{tools_str}]",
            "❌ 工具不存在"
        )
    except Exception as e:
        traceback.print_exc()
        return error_response(f"Fetch 执行失败: {str(e)}", "❌ Fetch异常")