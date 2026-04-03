import json
import os
import yaml
from src.plugins.route.agent_tool import call_agent_tool
from pathlib import Path
from typing import Dict, List, Optional, Any
from src.utils.config import LOCAL_TOOL_YAML, TOOL_INDEX_FILE

# 配置缓存
CONFIG_DATA = {}

def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)

def get_config_data():
    """获取配置数据"""
    return CONFIG_DATA


def load_local_tool_yaml():
    """加载本地工具配置"""
    global CONFIG_DATA
    if not os.path.exists(LOCAL_TOOL_YAML):
        with open(LOCAL_TOOL_YAML, "w") as f:
            pass
    with open(LOCAL_TOOL_YAML, "r", encoding="utf-8") as f:
            CONFIG_DATA = yaml.safe_load(f) or {}



BASE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_menu",
            "description": "获取当前可用的插件/服务总览菜单。你需要先通过此工具浏览有哪些功能可用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {"type": "string", "enum": ["local", "mcp", "extend"],
                              "description": "筛选查看的路由，必须指定三大 route 之一: local、mcp 或 extend"}
                },
                "required": ["route"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_tool",
            "description": "通过自然语言关键词搜索相关工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_tool",
            "description": "获取指定工具的详细信息，并将其立即加载到你的可用工具列表中。支持一次性加载同一个插件下的多个工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {"type": "string", "enum": ["local", "mcp", "extend"]},
                    "plugin_name": {"type": "string", "description": "插件名或 MCP Server 名"},
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "具体的工具名列表，支持一次性传入多个，如 ['search', 'get_video']"
                    }
                },
                "required": ["route", "plugin_name", "tool_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "加载指定的 Skill 并返回其详细信息和内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill 的名称"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_skill",
            "description": "按页列出所有可用的 Skill 并返回格式化字符串",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "页码，默认为 1"}
                }
            }
        }
    }
]

def fetch_tool_schemas(route: str, plugin_name: str, tool_names: list) -> list:
    """批量获取工具 schemas"""
    schemas = []
    if route == "local":
        try:
            load_local_tool_yaml()
            plugin_config = CONFIG_DATA.get(plugin_name, {})
            funcs = plugin_config.get("functions", {})
            for tool_name in tool_names:
                func_config = funcs.get(tool_name)
                if func_config and "function" in func_config:
                    schemas.append({"type": "function", "function": func_config["function"]})
        except Exception as e:
            print(f"❌ 读取 Local Schema 失败: {e}")
    elif route == "mcp":
        from src.plugins.route.mcp_tool import get_mcp_tool_schemas_sync
        # 一次性丢给底层去查
        schemas = get_mcp_tool_schemas_sync(plugin_name, tool_names)
    elif route == "extend":
        from src.plugins.route.extend_tool import get_extend_tool_schemas
        # 一次性丢给底层去查
        schemas = get_extend_tool_schemas(plugin_name, tool_names)

    return schemas if schemas else []


def parse_tool(tool_name: str, arguments: dict, route: str = None, plugin: str = None) -> tuple[str, dict]:
    """
    核心枢纽：统一处理工具调用的路由和执行。
    """
    new_schema_info = None
    result_content = ""

    try:
        # 1. 拦截：get_menu
        if tool_name == "get_menu":
            target_route = arguments.get("route", "all")
            result_content = get_menu(target_route)

        # 2. 拦截：search_tool
        elif tool_name == "search_tool":
            result_content = search_tool(arguments.get("query", ""))

        # 3. 拦截：fetch_tool (加载Schema闭环)
        elif tool_name == "fetch_tool":
            fetch_route = arguments.get("route")
            p_name = arguments.get("plugin_name")

            # 支持新版 tool_names 列表，也容错处理大模型发神经只传 tool_name 的情况
            t_names = arguments.get("tool_names", [])
            if not t_names and "tool_name" in arguments:
                t_names = [arguments.get("tool_name")]

            new_schema_info = []
            success_tools = []
            failed_tools = []

            # 核心修正：单次底层调用，批量获取！
            fetched_schemas = fetch_tool_schemas(fetch_route, p_name, t_names)

            # 转为字典方便后续核对状态
            fetched_dict = {s["function"]["name"]: s for s in fetched_schemas}

            for t_name in t_names:
                if t_name in fetched_dict:
                    schema_dict = fetched_dict[t_name]
                    real_func_name = schema_dict["function"]["name"]

                    if real_func_name in ["get_menu", "search_tool", "fetch_tool", "load_skill", "list_skill"]:
                        failed_tools.append(f"{t_name}(保留关键字被拒绝)")
                    else:
                        new_schema_info.append({
                            "route": fetch_route,
                            "plugin": p_name,
                            "funct": real_func_name,
                            "schema": schema_dict
                        })
                        success_tools.append(t_name)
                else:
                    failed_tools.append(t_name)

            # 拼装返回给大模型的结果
            res_messages = []
            if success_tools:
                res_messages.append(f"✅ 成功加载工具: {', '.join(success_tools)}。现已支持原生调用。")
            if failed_tools:
                res_messages.append(f"❌ 以下工具找不到或加载失败: {', '.join(failed_tools)}")

            result_content = "\n".join(res_messages)

        # 4. 拦截：load_skill
        elif tool_name == "load_skill":
            skill_name = arguments.get("name")
            result_content = load_skill(skill_name)

        # 5. 拦截：list_skill
        elif tool_name == "list_skill":
            page = arguments.get("page", 1)
            result_content = list_skill(page=page)

        else:
            from src.plugins.route.agent_tool import AGENT_TOOL_FUNCTIONS
            if tool_name in AGENT_TOOL_FUNCTIONS:
                result_content = call_agent_tool(tool_name, arguments)
            else:
                if not route or not plugin:
                    if os.path.exists(TOOL_INDEX_FILE):
                        with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                tool_info = json.loads(line)
                                if tool_info["func"] == tool_name:
                                    route = tool_info["route"]
                                    plugin = tool_info["plugin"]
                                    break

                if route == "local":
                    from src.plugins.route.local_tool import call_local_tool
                    result_content = call_local_tool(plugin, tool_name, arguments)
                elif route == "mcp":
                    from src.plugins.route.mcp_tool import call_mcp_tool
                    result_content = call_mcp_tool(plugin, tool_name, arguments)
                elif route == "extend":
                    from src.plugins.route.extend_tool import call_extend_tool
                    result_content = call_extend_tool(plugin, tool_name, arguments)
                else:
                    result_content = f"❌ 调度失败：未找到 {tool_name} 的底层路由映射。请确认它是否通过 fetch_tool 正常加载。"

    except Exception as e:
        result_content = f"❌ 工具调度/执行异常: {str(e)}"

    return str(result_content), new_schema_info


def get_menu(route: str) -> str:
    """获取工具菜单"""
    if route not in ["local", "mcp", "extend"]:
        return "❌ 无效的路由参数，必须指定三大 route 之一: local、mcp 或 extend"
        
    if not os.path.exists(TOOL_INDEX_FILE):
        # 如果 tool.jsonl 不存在，先初始化
        init_tool()
        if not os.path.exists(TOOL_INDEX_FILE):
            return "❌ 工具注册表未初始化，找不到 tool.jsonl。"

    tools = []
    try:
        with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                tool = json.loads(line)

                if tool["route"] == route:
                    tools.append(tool)
    except Exception as e:
        return f"❌ 读取工具菜单失败: {e}"

    if not tools:
        return f"当前路由 '{route}' 下没有可用的工具。"

    # 生成 Markdown 表格
    result = f"## 可用工具总览 (Route: {route})\n\n"
    result += "💡 提示：使用 fetch_tool 获取参数 Schema 后即可调用\n\n"
    result += "| plugin | func | desc |\n"
    result += "|--------|------|------|\n"
    
    for tool in tools:
        result += f"| {tool['plugin']} | {tool['func']} | {tool['desc']} |\n"
    
    result += f"\n**总计: {len(tools)} 个工具**"
    
    return result


def search_tool(query: str) -> str:
    """搜索工具"""
    if not os.path.exists(TOOL_INDEX_FILE):
        init_tool()
        if not os.path.exists(TOOL_INDEX_FILE):
            return "❌ 工具注册表未初始化，找不到 tool.jsonl"
    
    query_lower = query.lower()
    results = []
    with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            tool = json.loads(line)
            if (query_lower in tool['func'].lower() or
                    query_lower in tool['desc'].lower() or
                    query_lower in tool['plugin'].lower()):
                results.append(tool)
    
    if not results:
        return f"没有找到与 '{query}' 相关的工具。请尝试使用 get_menu 浏览所有工具。"
    
    res_str = f"【搜索结果】找到 {len(results)} 个与 '{query}' 相关的工具：\n"
    for t in results:
        res_str += f"\n🔧 工具名: {t['func']} (归属: {t['plugin']}, 路由: {t['route']})\n"
        res_str += f"   描述: {t['desc']}\n"
        res_str += f"   👉 获取指令: fetch_tool(route='{t['route']}', plugin_name='{t['plugin']}', tool_names=['{t['func']}'])\n"
    return res_str


def init_tool():
    tools_index = []
    try:
        from src.plugins.plugin_collection.local_manager import init_local_config_data
        init_local_config_data()
        if os.path.exists(LOCAL_TOOL_YAML):
            with open(LOCAL_TOOL_YAML, "r", encoding="utf-8") as f:
                local_config = yaml.safe_load(f) or {}
                for plugin_name, plugin_data in local_config.items():
                    functions = plugin_data.get("functions", {})
                    for func_name, func_data in functions.items():
                        desc = func_data.get("function", {}).get("description", "无描述")
                        tools_index.append({
                            "route": "local",
                            "plugin": plugin_name,
                            "func": func_name,
                            "desc": desc
                        })
    except Exception as e:
        pass
    try:
        from src.plugins.route.mcp_tool import extract_mcp_fingerprints_sync
        mcp_tools = extract_mcp_fingerprints_sync()
        if mcp_tools:
            tools_index.extend(mcp_tools)
    except Exception as e:
        print(f"❌ 扫描 MCP 工具异常: {e}")
    try:
        from src.plugins.route.extend_tool import extract_extend_fingerprints
        extend_tools = extract_extend_fingerprints()
        if extend_tools:
            tools_index.extend(extend_tools)
    except Exception as e:
        print(f"❌ 扫描 Extend 工具异常: {e}")
    try:
        with open(TOOL_INDEX_FILE, "w", encoding="utf-8") as f:
            for tool_info in tools_index:
                f.write(json.dumps(tool_info, ensure_ascii=False) + "\n")
    except Exception as e:
        pass


DEFAULT_SKILL_PATH = Path("data/skill")

def _parse_skill_md(file_path: Path) -> Dict[str, Any]:
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    metadata = {}
    content = text
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1]
            content = parts[2].strip()
            for line in frontmatter_str.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip()
    return {
        "metadata": metadata,
        "content": content
    }


def load_skill(name: str):
    skill_path = DEFAULT_SKILL_PATH
    base_dir = Path(skill_path)
    target_dir = base_dir / name
    md_file = target_dir / "SKILL.md"
    if not target_dir.is_dir() or not md_file.exists():
        return _format_response("text", f"Skill {name} not exist")
    parsed_data = _parse_skill_md(md_file)
    metadata = parsed_data["metadata"]
    desc = metadata.get("description", metadata.get("desc", ""))
    result = f"name: {name}\ndir_path: {str(target_dir.absolute())}\ndesc: {desc}\n---\ncontent:\n{parsed_data['content']}"
    return _format_response("text", result)


def list_skill(page: int = 1, size: int = 20) -> str:
    """按页列出所有可用的 Skill 并返回格式化字符串"""
    skill_path = DEFAULT_SKILL_PATH
    base_dir = Path(skill_path)

    if not base_dir.exists() or not base_dir.is_dir():
        return _format_response("text", "❌ Skill 目录不存在，未找到任何 Skill。")

    found_skills = []
    for item in base_dir.iterdir():
        if item.is_dir():
            md_file = item / "SKILL.md"
            if md_file.exists():
                parsed_data = _parse_skill_md(md_file)
                metadata = parsed_data["metadata"]
                desc = metadata.get("description", metadata.get("desc", "暂无描述"))
                skill_name = metadata.get("name", item.name)
                found_skills.append({
                    "name": skill_name,
                    "description": desc,
                    "dir_name": item.name,
                    "dir_path": str(item.absolute())
                })
    if not found_skills:
        return _format_response("text", "❌ 当前目录下没有找到包含 SKILL.md 的有效 Skill。")
    found_skills.sort(key=lambda x: x["dir_name"])
    total_skills = len(found_skills)
    total_pages = (total_skills + size - 1) // size
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
    start_idx = (page - 1) * size
    end_idx = start_idx + size
    paged_skills = found_skills[start_idx:end_idx]
    result = f"【可用 Skill 总览】共 {total_skills} 个，当前第 {page}/{total_pages} 页：\n"
    for skill in paged_skills:
        result += f"\n👉 Skill: {skill['name']}\n"
        result += f"   📝 描述: {skill['description']}\n"
    result += "\n💡 提示：使用 load_skill(name='skill_name') 获取完整内容与执行指南。"
    if page < total_pages:
        result += f"\n➡️ 翻页提示：当前页已满，请调用 list_skill(page={page + 1}) 查看下一页。"

    return _format_response("text", result)