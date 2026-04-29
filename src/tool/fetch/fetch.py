"""Fetch 工具主入口 - 统一调度 web/skill/mcp 三种获取方式"""

import json
import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from .exceptions import SkillNotFoundError, MCPNotFoundError, WebNetworkError
from .skill_fetch import load_skill
from .mcp_fetch import fetch_mcp_tools
from .web_content_fetch import web_content_fetch


def Fetch(source: str, name: str = None, serve_name: str = None, url: str = None, tool_names: list = None, **kwargs) -> str:
    """
    统一获取接口，支持三种获取方式：
    - web: 获取网页内容
    - skill: 加载技能文件
    - mcp: 获取 MCP 服务器的工具 Schema
    
    Args:
        source: 获取来源，必须为 "web"、"skill" 或 "mcp"
        
    针对不同 source 的参数：
        - web: url (必填) - 网页地址
        - skill: name (必填) - 技能名称
        - mcp: serve_name (必填), tool_names (可选) - MCP服务器名和工具名列表
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        # 1. 基础参数合法性拦截
        valid_sources = ["skill", "mcp", "web"]
        source = source.strip().lower() if source else ""
        if source not in valid_sources:
            return error_response(f"source参数不合法，合法参数有：{', '.join(valid_sources)}", "参数错误")

        # 2. 针对不同 source 的必填参数拦截
        if source == "skill":
            name = name or kwargs.get("name") or kwargs.get("skill_name")
            if not name:
                return error_response("搜索skill必须传入参数name", "参数缺失")
            
            result, error = load_skill(name)
            
        elif source == "mcp":
            serve_name = serve_name or kwargs.get("serve_name") or kwargs.get("server_name")
            tool_names = tool_names or kwargs.get("tool_names")
            
            # 支持单个工具名
            if not tool_names and "tool_name" in kwargs:
                tool_names = [kwargs.get("tool_name")]
                
            if not serve_name:
                return error_response("搜索mcp必须传入参数serve_name", "参数缺失")
                
            result, error = fetch_mcp_tools(serve_name, tool_names)
            
        elif source == "web":
            url = url or kwargs.get("url") or kwargs.get("web_url")
            if not url:
                return error_response("搜索web必须传入参数url", "参数缺失")
                
            result, error = web_content_fetch(url)

        # 处理错误返回
        if error:
            return warning_response(error, "获取失败")

        # 构建返回结果
        if source == "skill":
            return text_response({
                "name": result["name"],
                "description": result["description"],
                "content": result["content"],
                "directory": result["directory"]
            }, f"技能 '{name}' 加载完成")
            
        elif source == "mcp":
            if not result:
                return text_response({
                    "server_name": serve_name,
                    "tool_names": tool_names,
                    "schemas": [],
                    "message": "未找到匹配的工具"
                }, "未找到匹配工具")
            
            res_messages = []
            res_messages.append(f"✅ 成功从 MCP Server '{serve_name}' 获取工具:")
            res_messages.append("--- 以下是获取到的动态工具 Schema ---")
            
            for schema in result:
                res_messages.append(json.dumps(schema["function"], ensure_ascii=False))
            
            res_messages.append("-----")
            res_messages.append("⚠️ 注意：这些工具不在你的原生能力列表中，你必须使用 `call_dynamic_tool` 工具调用！")
            
            return text_response({
                "server_name": serve_name,
                "tool_names": [s["function"]["name"] for s in result],
                "schemas": result,
                "message": "\n".join(res_messages)
            }, f"MCP Schema 获取完成，共 {len(result)} 个工具")
            
        elif source == "web":
            md = f"# 📄 {result['title']}\n\n"
            md += f"**URL:** {result['url']}\n\n"
            md += f"**内容类型:** {result['content_type']}\n\n"
            md += "---\n\n"
            md += result.get("content", "")[:2000]
            
            return text_response({
                "url": result["url"],
                "title": result["title"],
                "content_type": result["content_type"],
                "content": result["content"],
                "markdown": md
            }, f"网页内容获取完成")

    except SkillNotFoundError as e:
        msg = (
            f"未在技能库中找到技能 {e.name}，请确保该技能：\n"
            "1.文件夹内含有SKILL.md并配置了相关字段\n"
            "2.Skill文件夹正确放置在技能库内"
        )
        return error_response(msg, "内容为空")
        
    except MCPNotFoundError as e:
        tools_str = str(e.tool_names) if isinstance(e.tool_names, list) else e.tool_names
        msg = (
            f"未在缓存文件中找到关于 {e.serve_name} 的对应MCP工具，请确保： \n"
            f"1.对应的 {tools_str} 工具存在于该MCP工具集中，可使用search工具进行搜索确保其存在\n"
            "2.你的老板正确进行了该MCP服务的白名单配置并安装对应的MCP\n"
            "也可能是老板刚安装上，需要重启PurrCat"
        )
        return error_response(msg, "内容为空")
        
    except WebNetworkError:
        msg = (
            "网络错误，请确保：\n"
            "1.网络正常\n"
            "2.老板正确配置了Tavily API"
        )
        return error_response(msg, "网络错误")
        
    except Exception as e:
        # 兜底未知报错
        traceback.print_exc()
        return error_response(f"Fetch 运行时异常: {str(e)}", "执行失败")