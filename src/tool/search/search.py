"""Search 工具主入口 - 统一调度 web/local/skill/mcp (API 与渲染完全解耦版)"""

import traceback
from typing import Dict, Any

from src.tool.search.mcp_search import mcp_search
from src.tool.search.skill_search import search_skills
from src.tool.search.web_search import web_search
from src.tool.utils.format import error_response, text_response, warning_response


def raw_search(route: str, query: str, topk: int = 5, **kwargs) -> Dict[str, Any]:
    """
    底层纯净的搜索 API，返回标准结构化字典（JSON 友好），供项目其他部分直接解析调用。
    
    返回字典结构示例:
    {
        "status": "success" | "warning" | "error",
        "message": "提示或错误信息",
        "route": "web" | "local" | "skill" | "mcp",
        "data": { ... 路由对应的数据 ... }
    }
    """
    try:
        route = route.strip().lower() if route else ""
        query = query.strip() if query else ""

        valid_routes = ["web", "local", "skill", "mcp"]
        if route not in valid_routes:
            return {
                "status": "error",
                "message": f"无效的路由类型: {route}。支持的路由: {', '.join(valid_routes)}",
                "data": {}
            }

        if not query:
            return {
                "status": "error",
                "message": "查询词不能为空",
                "data": {}
            }

        try:
            topk = int(topk) if topk else 5
            if topk > 15:
                topk = 15
        except ValueError:
            return {
                "status": "error",
                "message": "topk 参数必须是整数。",
                "data": {}
            }

        # ---- 路由 1: Web 互联网搜索 ----
        if route == "web":
            results, error = web_search(query, topk)
            if error:
                return {
                    "status": "warning",
                    "message": f"Web搜索失败: {error}",
                    "route": "web",
                    "data": {"results": []}
                }
            return {
                "status": "success",
                "message": f"成功获取 {len(results)} 条 Web 搜索结果",
                "route": "web",
                "data": {"results": results}
            }

        # ---- 路由 2, 3, 4: 本地能力搜索 (支持单查与混查) ----
        skill_results, skill_err = [], None
        mcp_results, mcp_err = [], None

        if route in ["local", "skill"]:
            skill_results, skill_err = search_skills(query, topk)
            
        if route in ["local", "mcp"]:
            mcp_results, mcp_err = mcp_search(query, topk)

        # 检查是否全部失败
        if (route == "skill" and skill_err) or \
           (route == "mcp" and mcp_err) or \
           (route == "local" and skill_err and mcp_err):
            return {
                "status": "warning",
                "message": f"搜索失败: Skill({skill_err}) | MCP({mcp_err})",
                "route": route,
                "data": {"skills": [], "mcp_tools": []}
            }

        return {
            "status": "success",
            "message": f"本地能力({route})检索成功",
            "route": route,
            "data": {
                "skills": skill_results or [],
                "mcp_tools": mcp_results or [],
                "errors": {
                    "skill_error": skill_err,
                    "mcp_error": mcp_err
                }
            }
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"搜索内核运行时异常: {str(e)}",
            "data": {}
        }


def Search(route: str, query: str, topk: int = 5, **kwargs) -> str:
    """
    面向大模型（LLM）的 Agent 工具接口。
    内部调用 raw_search API，并将结构化 JSON 数据清洗、转换为极限压缩 Token 的 Markdown 文本。
    """
    api_response = raw_search(route, query, topk, **kwargs)
    
    status = api_response["status"]
    message = api_response["message"]
    
    if status == "error":
        return error_response(message, "参数错误" if "参数" in message else "系统错误")
    if status == "warning":
        return warning_response(message, f"⚠️ {api_response['route']}搜索失败")

    route_type = api_response["route"]
    response_data = api_response["data"]

    # ---- 渲染 Web 结果 ----
    if route_type == "web":
        results = response_data["results"]
        md = f"# Result: {query}\n\n"
        for i, res in enumerate(results, 1):
            md += f"## {i}. {res['title']}\n**URL:** {res['url']}\n\n**Snip:** {res['snippet']}\n\n---\n\n"
        md += "Tips：如果需要阅读完整详情，请使用 `Fetch` 工具 (source='web') 并传入对应的 URL。**"
        return text_response(md, f"🌐 Web | {len(results)}条结果")

    # ---- 渲染 Local/Skill/MCP 结果 ----
    skills = response_data.get("skills", [])
    mcp_tools = response_data.get("mcp_tools", [])
    
    lines = [f"# 本地能力检索结果 [{route_type}] (Top{topk}):"]
    
    if route_type in ["local", "skill"]:
        lines.append("\n## Skills:")
        if not skills:
            lines.append("（未找到匹配的本地技能）")
        for res in skills:
            skill = res.get("skill", {})
            desc = skill.get("description", "无")[:80].replace("\n", " ")
            lines.append(f"- [Skill] {skill.get('name', 'unknown')} (得分: {res.get('score', 0)}) - {desc}")

    if route_type in ["local", "mcp"]:
        lines.append("\n## MCP Tools:")
        if not mcp_tools:
            lines.append("（未找到匹配的 MCP 工具）")
        for res in mcp_tools:
            desc = res.get("description", "无")[:80].replace("\n", " ")
            lines.append(f"- [MCP:{res.get('server_name', 'unknown')}] {res.get('tool_name', 'unknown')} (得分: {res.get('score', 0)}) - {desc}")

    lines.append("\nTips: 若需使用上述能力，请使用 `Fetch` 工具获取完整参数与细节。")
    
    total_hits = len(skills) + len(mcp_tools)
    return text_response("\n".join(lines), f"🔧 {route_type.capitalize()} | 命中{total_hits}个能力")