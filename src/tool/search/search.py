"""Search 工具主入口 - 统一调度 web/skill/mcp 三种搜索方式"""

import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.search.exceptions import (
    SearchError,
    InvalidRouteError,
    MissingParameterError
)
from src.tool.search.web_search import web_search
from src.tool.search.skill_search import search_skills, load_skill


def Search(route: str, query: str, topk: int = 5, **kwargs) -> str:
    """
    统一搜索接口，支持三种搜索方式：web（互联网搜索）、skill（技能搜索）、mcp（MCP服务器搜索）
    
    Args:
        route: 搜索路由，必须为 "web"、"skill" 或 "mcp"
        query: 搜索查询词（必填）
        topk: 返回结果数量，默认 5
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        # 参数校验
        route = route.strip().lower() if route else ""
        query = query.strip() if query else ""
        
        # 检查路由类型
        if route not in ["web", "skill", "mcp"]:
            return error_response(
                f"无效的路由类型: {route}。支持的路由: web, skill, mcp",
                "参数错误"
            )
        
        # 检查查询词
        if not query:
            return error_response("查询词不能为空", "参数错误")
        
        # 检查 topk 范围：设置安全上限，防止 DDoS 自身或 Token 溢出
        try:
            topk = int(topk) if topk else 5
            if topk > 15:
                topk = 15
        except ValueError:
            return error_response("topk 参数必须是整数。", "参数错误")
        
        # 根据路由执行搜索
        if route == "web":
            return _search_web(query, topk)
        elif route == "skill":
            return _search_skill(query, topk)
        elif route == "mcp":
            return _search_mcp(query, topk)
        
        return error_response("未知错误", "系统错误")
        
    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"搜索运行时异常: {str(e)}", "执行失败")


def _search_web(query: str, topk: int) -> str:
    """执行互联网搜索"""
    try:
        results, error = web_search(query, topk)
        
        if error:
            return warning_response(error, "搜索失败")
        
        # 构建 Markdown 格式结果
        md = f"# 🔍 搜索结果: {query}\n\n"
        for i, res in enumerate(results, 1):
            md += f"### {i}. {res['title']}\n"
            md += f"- URL: {res['url']}\n"
            md += f"- {res['snippet'][:500]}\n\n"
        
        return text_response({
            "query": query,
            "results_count": len(results),
            "markdown": md,
            "results": results
        }, f"Web 搜索完成，找到 {len(results)} 条结果")
    
    except Exception as e:
        return error_response(f"Web 搜索异常: {e}", "搜索异常")


def _search_skill(query: str, topk: int) -> str:
    """执行技能搜索"""
    try:
        results, error = search_skills(query, topk)
        
        if error:
            return warning_response(error, "搜索失败")
        
        if not results:
            return text_response({
                "query": query,
                "results_count": 0,
                "message": "未找到匹配度较高的可用技能"
            }, "未找到匹配技能")
        
        # 构建表格格式结果
        result_text = f"🎯 技能搜索结果 (Top {topk}):\n\n"
        result_text += "| 技能名称 | 匹配得分 | 描述 |\n"
        result_text += "|----------|----------|------|\n"
        
        for res in results:
            skill = res["skill"]
            result_text += f"| {skill.get('name', 'unknown')} | {res['score']} | {skill.get('description', '无描述')} |\n"
        
        result_text += "\n💡 提示：使用 load_skill(name='技能名称') 获取完整内容与执行指南"
        
        return text_response({
            "query": query,
            "results_count": len(results),
            "results": results,
            "markdown": result_text
        }, f"Skill 搜索完成，找到 {len(results)} 条结果")
    
    except Exception as e:
        return error_response(f"Skill 搜索异常: {e}", "搜索异常")


def _search_mcp(query: str, topk: int) -> str:
    """执行 MCP 搜索"""
    try:
        from src.tool.search.mcp_search import mcp_search
        
        results, error = mcp_search(query, topk)
        
        if error:
            return warning_response(error, "MCP 搜索不可用")
        
        return text_response({
            "query": query,
            "results_count": len(results),
            "results": results
        }, f"MCP 搜索完成，找到 {len(results)} 条结果")
    
    except ImportError:
        return warning_response("MCP 模块未安装，无法使用 MCP 搜索", "依赖缺失")
    except Exception as e:
        return error_response(f"MCP 搜索异常: {e}", "搜索异常")