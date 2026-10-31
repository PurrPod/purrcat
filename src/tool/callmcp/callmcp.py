import json
import time
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


def _open_url_in_builtin_browser(url: str) -> bool:
    """请宿主（Electron 主进程）在内置浏览器中打开一个用户可见的标签页。

    宿主控制口只监听回环地址，端口与令牌写在 ~/.purrcat/run/control.json。
    """
    import os
    import urllib.request

    state_file = os.path.join(
        os.path.expanduser("~"), ".purrcat", "run", "control.json"
    )
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        port = int(state.get("port") or 0)
        token = str(state.get("token") or "")
        if not port or not token:
            return False
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/control/browser/open-url",
            data=json.dumps({"url": url}).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-purrcat-token": token,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception as err:
        print(f"[CallMCP] 内置浏览器回落失败: {err}")
        return False


def _new_page_fallback(server_name: str, tool_name: str, args: dict, message: str):
    """chrome-devtools 的 new_page 依赖 CDP Target.createTarget，Electron 不支持。

    命中该错误时改为让宿主在内置浏览器里开一个可见标签页，并把最新页面列表回给 Agent。
    """
    if server_name != "chrome-devtools" or tool_name != "new_page":
        return None
    if "Target.createTarget" not in message:
        return None
    url = str(args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    if not _open_url_in_builtin_browser(url):
        return None
    time.sleep(0.8)  # 等内置浏览器标签页创建完成，便于紧接的 list_pages 看到它
    page_list = ""
    try:
        page_list = "\n".join(call_mcp_tool(server_name, "list_pages", {}))
    except Exception:
        pass
    body = (
        f"宿主已在你的内置浏览器中新开标签页并加载：{url}\n"
        "（Electron 的 CDP 不支持 Target.createTarget，因此改为由宿主直接创建内置浏览器标签页。）"
    )
    if page_list:
        body += (
            f"\n当前页面列表：\n{page_list}\n"
            "请使用与该 URL 匹配的页面；禁止操作标题为「PurrCat · 极简模式」的页面。"
        )
    else:
        body += "\n请调用 list_pages 获取新标签页的 pageId，再继续操作。"
    return text_response(body, "✅ 已在内置浏览器新开标签页")


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
                f"{server_name}不在配置里，请确保用户已为你配置该MCP，如果是刚刚配置的MCP，请提醒用户需要重启系统才能生效。当前已配置MCP:{mcp_list}\n或者也可用search工具搜索其它满足需求的mcp",
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

        except ToolExecutionError as err:
            fallback = _new_page_fallback(server_name, tool_name, args, str(err))
            if fallback:
                return fallback
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
            fallback = _new_page_fallback(server_name, tool_name, args, str(e))
            if fallback:
                return fallback
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
            print(
                f"✅ 检测到本地已有 MCP 缓存 ({MCP_SCHEMA_CACHE_FILE})，跳过全量拉取。如需刷新请调用 reload_mcp_schema 工具。"
            )
            return

        print("⚠️ 未检测到 mcp_schema.json，正在进行首次全量拉取...")
        schemas = fetch_and_cache_schemas()
        print(f"✅ 成功完成首次 [MCP] 缓存加载，共 {len(schemas)} 个 Schema")
    except Exception as e:
        print(f"❌ 初始化 [MCP] 异常: {e}")
        traceback.print_exc()


def reload_mcp_schema_core() -> int:
    """重建 MCP Schema 缓存并热更新内存检索树，返回重载到的工具总数。

    配置已变化的 Server 会在 get_session 的指纹比对处自动重启子进程，
    新增的 Server 则在此刻首次拉起。Agent 工具 reload_mcp_schema 与
    配置中心「MCP」页的「重载到内存」按钮共用这一实现，避免逻辑漂移。
    """
    schemas = refresh_schemas()

    from src.tool.search.mcp_search import MCPSearcher, rebuild_vectors_async

    MCPSearcher().reload_index()
    rebuild_vectors_async()
    return len(schemas)


def reload_mcp_schema():
    """手动刷新 MCP Schema 缓存：重建 json 缓存并重载到内存重新向量化"""
    try:
        count = reload_mcp_schema_core()

        return text_response(
            {
                "message": f"✅ Schema 重新握手并写入缓存成功！内存检索树已热更新。共载入 {count} 个工具。"
            },
            "",
        )
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e), "❌ 刷新失败")
