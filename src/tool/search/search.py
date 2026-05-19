"""Search 工具主入口 - 统一调度 web/local 两种搜索方式"""

import traceback

from src.tool.search.mcp_search import mcp_search
from src.tool.search.skill_search import search_skills
from src.tool.search.web_search import web_search
from src.tool.utils.format import error_response, text_response, warning_response


def Search(route: str, query: str, topk: int = 5, **kwargs) -> str:
    """
    统一搜索接口，支持两种搜索方式：
    - web: 互联网搜索
    - local: 本地 Skill 与 MCP 工具搜索（合并返回）

    Args:
        route: 搜索路由，必须为 "web" 或 "local"
        query: 搜索查询词（必填）
        topk: 返回结果数量，默认 5

    Returns:
        格式化后的 JSON 字符串
    """
    try:
        route = route.strip().lower() if route else ""
        query = query.strip() if query else ""

        if route not in ["web", "local"]:
            return error_response(
                f"无效的路由类型: {route}。支持的路由: web, local", "参数错误"
            )

        if not query:
            return error_response("查询词不能为空", "参数错误")

        try:
            topk = int(topk) if topk else 5
            if topk > 15:
                topk = 15
        except ValueError:
            return error_response("topk 参数必须是整数。", "参数错误")

        if route == "web":
            return _search_web(query, topk)
        elif route == "local":
            return _search_local(query, topk)

        return error_response("未知错误", "系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"搜索运行时异常: {str(e)}", "执行失败")


def _search_web(query: str, topk: int) -> str:
    """执行互联网搜索（纯检索）"""
    try:
        results, error = web_search(query, topk)

        if error:
            return warning_response(error, "⚠️ Web搜索失败")

        md = f"# 🔍 搜索结果: {query}\n\n"
        for i, res in enumerate(results, 1):
            md += f"## {i}. {res['title']}\n"
            md += f"**URL:** {res['url']}\n\n"
            md += f"**摘要:** {res['snippet']}\n\n"
            md += "---\n\n"

        # ✨【关键】：在这里通过 Prompt 引导大模型去调用 Fetch 实现解耦的深度阅读
        md += "💡 **提示：如果需要阅读上述某篇报道的完整详情，请使用 `Fetch` 工具 (source='web') 并传入对应的 URL。**"

        return text_response(
            {
                "query": query,
                "results_count": len(results),
                "markdown": md,
                "results": results,
            },
            f"🌐 Web | {len(results)}条结果",
        )

    except Exception as e:
        return error_response(f"Web 搜索异常: {e}", "❌ Web搜索异常")


def _search_local(query: str, topk: int) -> str:
    """合并搜索本地 Skill、MCP 工具与 Memo 记忆"""
    try:
        # 1. 分别搜索 Skill 与 MCP
        skill_results, skill_err = search_skills(query, topk)
        mcp_results, mcp_err = mcp_search(query, topk)
        
        # 2. 新增：搜索 Memo 记忆
        memo_results, memo_err = [], None
        try:
            from src.memory import search_memory as memory_search
            memo_results = memory_search(query=query, filters={\"top_k\": topk})
        except Exception as e:
            memo_err = str(e)

        if skill_err and mcp_err and memo_err:
            return warning_response(
                f"Skill搜索失败: {skill_err}\nMCP搜索失败: {mcp_err}\nMemo搜索失败: {memo_err}", "⚠️ Local全部失败"
            )

        merged_results = []

        # -- 组装 Skill 结果 --
        for res in skill_results or []:
            skill = res.get("skill", {})
            merged_results.append(
                {
                    "source": "Skill",
                    "name": skill.get("name", "unknown"),
                    "description": skill.get("description", "无描述"),
                    "score": res.get("score", 0),
                }
            )

        # -- 组装 MCP 结果 --
        for res in mcp_results or []:
            merged_results.append(
                {
                    "source": f"MCP ({res.get('server_name', 'unknown')})",
                    "name": res.get("tool_name", "unknown"),
                    "description": res.get("description", "无描述"),
                    "score": res.get("score", 0),
                }
            )
            
        # -- 组装 Memo 结果 --
        for res in memo_results or []:
            if isinstance(res, dict):
                score = res.get("score", res.get("similarity", 0))
                desc = res.get("content", res.get("text", res.get("event", str(res))))
                name = res.get("type", "Memory")
            else:
                score = 0
                desc = str(res)
                name = "Memory"
                
            desc_str = str(desc).replace("\n", " ").replace("|", "｜")
            if len(desc_str) > 150:
                desc_str = desc_str[:147] + "..."

            merged_results.append(
                {
                    "source": "Memo",
                    "name": str(name).replace("|", "｜"),
                    "description": desc_str,
                    "score": float(score) if score is not None else 0.0,
                }
            )

        merged_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_results = merged_results[:topk]

        if not top_results:
            return text_response({"query": query, "results_count": 0}, "🔍 Local无结果")

        skill_count = len([r for r in top_results if r["source"] == "Skill"])
        mcp_count = len([r for r in top_results if r["source"].startswith("MCP")])
        memo_count = len([r for r in top_results if r["source"] == "Memo"])
        
        md = f"🎯 本地混合搜索结果 (Top {len(top_results)}):\n\n"
        md += "| 来源类别 | 名称/类型 | 匹配得分 | 描述/内容 |\n"
        md += "|----------|-----------|----------|-----------|\n"

        for item in top_results:
            md += f"| {item['source']} | `{item['name']}` | {item['score']} | {item['description']} |\n"

        md += "\n💡 **提示：你可以使用 `Fetch` 工具获取上述技能或 MCP 工具的完整细节。**"
        
        return text_response(
            {
                "query": query,
                "results_count": len(top_results),
                "results": top_results,
                "markdown": md,
            },
            f"🔧 Local | Skill:{skill_count} MCP:{mcp_count} Memo:{memo_count}",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(f"Local搜索异常: {e}", "❌ Local异常")
