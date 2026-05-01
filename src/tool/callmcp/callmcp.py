import json
import traceback
import threading
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.callmcp.exceptions import MCPError, ServerNotFoundError, ToolExecutionError
from src.tool.callmcp.tool_caller import call_mcp_tool
from src.tool.callmcp.schema_manager import load_cached_schemas, refresh_schemas, fetch_and_cache_schemas
from src.tool.callmcp.session_manager import load_configs


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
                "❌ MCP未配置"
            )

        # 2. 获取并检查 tool_name 是否存在
        schemas = load_cached_schemas()
        server_schemas = [s for s in schemas if s.get("server") == server_name]
        tool_list = [s.get("function", {}).get("name") for s in server_schemas]

        if tool_name not in tool_list:
            return error_response(
                f"{server_name}MCP里仅有如下工具：{tool_list}，没有这个工具",
                ""
            )

        # 3. 提取具体的 tool_schema 以备报错使用
        tool_schema = next((s.get("function", {}) for s in server_schemas if s.get("function", {}).get("name") == tool_name), {})

        # 4. 调用工具，捕获参数异常
        try:
            result = call_mcp_tool(server_name, tool_name, args)
            return text_response(result, f"✅ {tool_name}成功")

        except ToolExecutionError as e:
            # 捕获参数不匹配、缺少参数等错误
            param_schema_str = json.dumps(tool_schema.get('parameters', {}), ensure_ascii=False)
            return error_response(
                f"{server_name}.{tool_name} 参数列表：{param_schema_str}",
                "❌ 参数错误"
            )
        except ServerNotFoundError as e:
            return error_response(str(e), "❌ 服务器未找到")
        except MCPError as e:
            return warning_response(str(e), "⚠️ 执行警告")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"MCP调用异常: {str(e)}", "❌ MCP异常")


def initialize_mcp():
    """后台初始化 MCP 连接与拉取完整 Schema 缓存"""
    print("正在后台初始化 [MCP] 连接与 Schema...")
    def _bg_init():
        try:
            schemas = fetch_and_cache_schemas()
            print(f"成功加载 [MCP] 缓存，共 {len(schemas)} 个 Schema")
        except Exception as e:
            print(f"后台初始化 [MCP] 异常: {e}")

    thread = threading.Thread(target=_bg_init, daemon=True)
    thread.start()
    return True


def refresh_mcp_schemas():
    """手动刷新 MCP Schema 缓存"""
    try:
        schemas = refresh_schemas()
        return text_response({"message": f"Schema 刷新成功，共 {len(schemas)} 个工具。"}, "")
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e), "")