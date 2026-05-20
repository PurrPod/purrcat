import json
import threading
import traceback

from src.tool.callmcp.exceptions import (
    MCPError,
    ServerNotFoundError,
    ToolExecutionError,
)
from src.tool.callmcp.schema_manager import (
    fetch_and_cache_schemas,
    load_cached_schemas,
    refresh_schemas,
)
from src.tool.callmcp.session_manager import load_configs
from src.tool.callmcp.tool_caller import call_mcp_tool
from src.tool.utils.format import error_response, text_response, warning_response
from src.utils.config import MCP_SCHEMA_CACHE_FILE


def CallMCP(server_name: str, tool_name: str, arguments: dict = None, **kwargs) -> str:
    """
    调用 MCP 服务器工具
    """
    try:
        if not server_name or not str(server_name).strip():
            return error_response("缺少 server_name 参数", "❌ 参数错误")
        if not tool_name or not str(tool_name).strip():
            return error_response("缺少 tool_name 参数", "❌ 参数错误")

        args = arguments or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return error_response("arguments 必须是合法的 JSON", "❌ 参数解析错误")

        # 1. 检查 server_name 是否在配置中
        configs = load_configs()
        if server_name not in configs:
            mcp_list = list(configs.keys())
            return error_response(
                f"{server_name}不在配置里，请确保老板已为你配置该MCP，如果是刚刚配置的MCP，请提醒老板需要重启系统才能生效。当前已配置MCP:{mcp_list}\n或者也可用search工具搜索其它满足需求的mcp",
                "❌ MCP未配置",
            )

        # 2. 获取并检查 tool_name 是否存在
        schemas = load_cached_schemas()
        server_schemas = [s for s in schemas if s.get("server") == server_name]
        tool_list = [s.get("function", {}).get("name") for s in server_schemas]

        if tool_name not in tool_list:
            return error_response(
                f"{server_name}MCP里仅有如下工具：{tool_list}，没有这个工具", ""
            )

        # 3. 提取具体的 tool_schema 以备报错使用
        tool_schema = next(
            (
                s.get("function", {})
                for s in server_schemas
                if s.get("function", {}).get("name") == tool_name
            ),
            {},
        )

        # 4. 调用工具，捕获参数异常
        try:
            result = call_mcp_tool(server_name, tool_name, args)
            return text_response(result, f"✅ {tool_name}成功")

        except ToolExecutionError:
            # 捕获参数不匹配、缺少参数等错误
            param_schema_str = json.dumps(
                tool_schema.get("parameters", {}), ensure_ascii=False
            )
            return error_response(
                f"{server_name}.{tool_name} 参数列表：{param_schema_str}", "❌ 参数错误"
            )
        except ServerNotFoundError as err:
            return error_response(str(err), "❌ 服务器未找到")
        except MCPError as e:
            return warning_response(str(e), "⚠️ 执行警告")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"MCP调用异常: {str(e)}", "❌ MCP异常")


def initialize_mcp_sync():
    """同步初始化：检查式启动，全量拉取留给用户或统一后台线程触发"""
    print("正在检查 [MCP] Schema 缓存状态...")
    try:
        import os
        if os.path.exists(MCP_SCHEMA_CACHE_FILE):
            print(f"✅ 检测到本地已有 MCP 缓存 ({MCP_SCHEMA_CACHE_FILE})，跳过全量拉取。如需刷新请调用 reload_mcp_schema 工具。")
            return

        print("⚠️ 未检测到 mcp_schema.json，正在进行首次全量拉取...")
        schemas = fetch_and_cache_schemas()
        print(f"✅ 成功完成首次 [MCP] 缓存加载，共 {len(schemas)} 个 Schema")
    except Exception as e:
        print(f"❌ 初始化 [MCP] 异常: {e}")
        traceback.print_exc()


def reload_mcp_schema():
    """手动刷新 MCP Schema 缓存：重建 json 缓存并重载到内存重新向量化"""
    try:
        schemas = refresh_schemas()

        from src.tool.search.mcp_search import MCPSearcher
        MCPSearcher().reload_index()

        return text_response(
            {"message": f"✅ Schema 重新握手并写入缓存成功！内存检索树已热更新。共载入 {len(schemas)} 个工具。"}, ""
        )
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e), "❌ 刷新失败")
