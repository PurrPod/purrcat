"""Fetch 工具主入口 - 统一调度 web/skill/mcp 三种获取方式"""

import json
import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.fetch.exceptions import (
    FetchError,
    InvalidSourceError,
    MissingParameterError
)
from src.tool.fetch.web_content_fetch import web_content_fetch
from src.tool.fetch.skill_fetch import load_skill
from src.tool.fetch.mcp_fetch import fetch_mcp_tools


def Fetch(source: str, **kwargs) -> str:
    """
    统一获取接口，支持三种获取方式：
    - web: 获取网页内容
    - skill: 加载技能文件
    - mcp: 获取 MCP 服务器的工具 Schema（fetch_tool 的精简版，仅保留 MCP 来源）
    
    Args:
        source: 获取来源，必须为 "web"、"skill" 或 "mcp"
        
    针对不同 source 的参数：
        - web: url (必填) - 网页地址
        - skill: name (必填) - 技能名称
        - mcp: server_name (必填), tool_names (可选) - MCP服务器名和工具名列表
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        # 参数校验
        source = source.strip().lower() if source else ""
        
        # 检查来源类型
        if source not in ["web", "skill", "mcp"]:
            return error_response(
                f"无效的来源类型: {source}。支持的来源: web, skill, mcp",
                "参数错误"
            )
        
        # 根据来源类型执行获取
        if source == "web":
            return _fetch_web(**kwargs)
        elif source == "skill":
            return _fetch_skill(**kwargs)
        elif source == "mcp":
            return _fetch_mcp(**kwargs)
        
        return error_response("未知错误", "系统错误")
        
    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"获取运行时异常: {str(e)}", "执行失败")


def _fetch_web(**kwargs) -> str:
    """获取网页内容"""
    url = kwargs.get("url") or kwargs.get("web_url")
    
    if not url:
        return error_response("缺少必需参数: url", "参数错误")
    
    try:
        result, error = web_content_fetch(url)
        
        if error:
            return warning_response(error, "获取失败")
        
        # 构建结果
        md = f"# 📄 {result['title']}\n\n"
        md += f"**URL:** {result['url']}\n\n"
        md += f"**内容类型:** {result['content_type']}\n\n"
        md += "---\n\n"
        md += result.get("content", "")[:2000]  # 限制长度
        
        return text_response({
            "url": result["url"],
            "title": result["title"],
            "content_type": result["content_type"],
            "content": result["content"],
            "markdown": md
        }, f"网页内容获取完成")
    
    except Exception as e:
        return error_response(f"网页获取异常: {e}", "获取异常")


def _fetch_skill(**kwargs) -> str:
    """加载技能文件"""
    name = kwargs.get("name") or kwargs.get("skill_name")
    
    if not name:
        return error_response("缺少必需参数: name", "参数错误")
    
    try:
        result, error = load_skill(name)
        
        if error:
            return warning_response(error, "获取失败")
        
        return text_response({
            "name": result["name"],
            "description": result["description"],
            "content": result["content"],
            "directory": result["directory"]
        }, f"技能 '{name}' 加载完成")
    
    except Exception as e:
        return error_response(f"技能加载异常: {e}", "获取异常")


def _fetch_mcp(**kwargs) -> str:
    """获取 MCP 工具 Schema"""
    server_name = kwargs.get("server_name")
    tool_names = kwargs.get("tool_names", [])
    
    if not server_name:
        return error_response("缺少必需参数: server_name", "参数错误")
    
    # 支持单个工具名
    if not tool_names and "tool_name" in kwargs:
        tool_names = [kwargs.get("tool_name")]
    
    try:
        schemas, error = fetch_mcp_tools(server_name, tool_names)
        
        if error:
            return warning_response(error, "获取失败")
        
        if not schemas:
            return text_response({
                "server_name": server_name,
                "tool_names": tool_names,
                "schemas": [],
                "message": "未找到匹配的工具"
            }, "未找到匹配工具")
        
        # 构建结果消息
        res_messages = []
        res_messages.append(f"✅ 成功从 MCP Server '{server_name}' 获取工具:")
        res_messages.append("--- 以下是获取到的动态工具 Schema ---")
        
        for schema in schemas:
            res_messages.append(json.dumps(schema["function"], ensure_ascii=False))
        
        res_messages.append("-----")
        res_messages.append("⚠️ 注意：这些工具不在你的原生能力列表中，你必须使用 `call_dynamic_tool` 工具调用！")
        
        return text_response({
            "server_name": server_name,
            "tool_names": [s["function"]["name"] for s in schemas],
            "schemas": schemas,
            "message": "\n".join(res_messages)
        }, f"MCP Schema 获取完成，共 {len(schemas)} 个工具")
    
    except Exception as e:
        return error_response(f"MCP 获取异常: {e}", "获取异常")