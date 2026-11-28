import json
import traceback

from src.tool.utils.format import error_response, text_response, warning_response

from .exceptions import (
    MCPRefreshInProgressError,
    MCPServerNotFoundError,
    MCPToolNotFoundError,
)
from .mcp_fetch import fetch_mcp_tools
from .skill_fetch import load_skill
from .web_content_fetch import web_content_fetch


def Fetch(
    source: str,
    name: str = None,
    serve_name: str = None,
    url: str = None,
    tool_names: list = None,
    **kwargs,
) -> str:
    try:
        valid_sources = ["skill", "mcp", "web"]
        source = source.strip().lower() if source else ""
        if source not in valid_sources:
            return error_response(
                f"source 必须是以下之一: {', '.join(valid_sources)}", ""
            )

        result = None
        error = None

        if source == "skill":
            name = name or kwargs.get("name") or kwargs.get("skill_name")
            if not name:
                return error_response("获取 skill 缺少必要参数 name", "")
            result, error = load_skill(name)

        elif source == "mcp":
            serve_name = (
                serve_name or kwargs.get("serve_name") or kwargs.get("server_name")
            )
            tool_names = tool_names or kwargs.get("tool_names")
            if not tool_names and "tool_name" in kwargs:
                tool_names = [kwargs.get("tool_name")]

            if not serve_name:
                from src.tool.callmcp.session_manager import load_configs

                configs = load_configs()
                mcp_list = list(configs.keys())
                msg = "使用 Fetch(source='mcp', server_name='xxx') 获取工具详情"
                return text_response(
                    {"configured_servers": mcp_list, "message": msg},
                    f"{len(mcp_list)}个MCP",
                )

            result, error = fetch_mcp_tools(serve_name, tool_names)

        elif source == "web":
            url = url or kwargs.get("url") or kwargs.get("web_url")
            if not url:
                return error_response("获取 web 缺少必要参数 url", "")
            result, error = web_content_fetch(url)

        if error:
            return warning_response(error, f"{source.upper()} 获取失败")

        if source == "skill":
            # 直接把完整 SOP 作为 tool result 返回（route 层 _safe_truncate 会兜底超长内容）
            # 注意：不要在此处 agent_force_push —— fetch 属于子进程隔离工具，
            # 子进程里的 AgentManager 是孤儿实例，push 内容会随子进程退出丢失
            skill_instruction = (
                f"技能: {result['name']}\n"
                f"沙盒技能目录(已从主库同步最新): {result['directory']}\n"
                f"描述: {result['description']}\n\n"
                f"[技能SOP操作指南]\n{result['content']}\n\n"
                f"请严格按照上述步骤与约束进行操作。技能附属资源(脚本/模板等)已同步到上述沙盒目录，可直接使用。"
            )

            return text_response(skill_instruction, f"Skill [{name}]")

        elif source == "mcp":
            if not result:
                return text_response(
                    "暂无工具 Schema",
                    "暂无Schema",
                )

            res_messages = []
            res_messages.append(f"成功找到 MCP Server '{serve_name}' 的工具信息。")

            # 根据是否指定了 tool_names，决定标题和输出的详细程度
            res_messages.append(
                "--- 工具列表 ---" if not tool_names else "--- 工具 Schema ---"
            )

            for schema in result:
                func = schema.get("function", {})
                if not tool_names:
                    # 渐进式披露：只显示名称和描述，省略长篇大论的 parameters
                    name = func.get("name", "unknown")
                    desc = func.get("description", "无描述")
                    res_messages.append(f"- **{name}**: {desc}")
                else:
                    # 精确查询时：完整输出包含 parameters 的 Schema
                    res_messages.append(json.dumps(func, ensure_ascii=False))

            res_messages.append("-----")
            res_messages.append("请使用 `CallMCP` 调用这些工具。")

            # 动态调整尾部提示语
            if not tool_names:
                res_messages.append(
                    "提示：如果需要获取更详细的参数说明，请再指定具体工具名 (`tool_names`)。"
                )
            else:
                res_messages.append(
                    "如需更多工具，不传 tool_names 即可列出该 Server 下的全部工具。"
                )

            # 改造：直接返回 "\n".join() 拼接好的字符串
            return text_response(
                "\n".join(res_messages), f"{serve_name} | {len(result)}个工具"
            )

        elif source == "web":
            content_len = len(result.get("content", ""))
            # 改造：直接返回 md 字符串，移除截断限制
            md = f"# {result['title']}\n\n**URL:** {result['url']}\n**类型:** {result['content_type']}\n---\n\n{result.get('content', '')}"
            return text_response(md, f"{content_len}字符")

    except MCPServerNotFoundError as e:
        servers_str = (
            ", ".join(e.available_servers) if e.available_servers else "无可用"
        )
        return error_response(
            f"无法找到 MCP 服务器 '{e.serve_name}'。当前可用: [{servers_str}]",
            "服务器未找到",
        )
    except MCPRefreshInProgressError as e:
        return warning_response(
            f"MCP Schema 缓存正在刷新中（通常是刚合并 MCP 后的热加载，需要对所有 server "
            f"重新冷启动握手，一般数十秒）。\n"
            f"本次查询 '{e.serve_name}' 的结果不可信——**不代表该服务器不存在**；"
            f"工具本身此时已可正常调用。\n"
            f"请稍候重试本次 fetch，或先 `Fetch(source='mcp')` 查看当前已注册的服务器列表。",
            "缓存刷新中",
        )
    except MCPToolNotFoundError as e:
        tools_str = ", ".join(e.available_tools) if e.available_tools else "无"
        return error_response(
            f"在 '{e.serve_name}' 中找不到工具 '{e.tool_name}'。现有工具: [{tools_str}]",
            "工具不存在",
        )
    except Exception as e:
        traceback.print_exc()
        return error_response(f"Fetch 执行失败: {str(e)}", "Fetch异常")
