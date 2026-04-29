import atexit
import os
import sys
import json
import uuid
import re
import threading
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any

import docker
import pexpect
from docker.errors import DockerException, NotFound

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from src.utils.config import LOCAL_TOOL_YAML, TOOL_INDEX_FILE

# 配置缓存
CONFIG_DATA = {}


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


def _format_response(msg_type: str, content: Any) -> str:
    """统一的工具返回格式"""
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)

BASE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "在安全的沙盒环境 (Docker) 中执行 Shell 命令。你可以使用此工具进行环境配置、代码运行、文件操作等。注意：每次使用 cat >> 写入文件时，严禁超过 50 行代码，写完必须结束当前调用，在下一次回复中继续追加。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 Shell 命令（支持连串命令和多行文本，请注意正确的引号转义）"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "命令执行的超时时间（秒），如果不确定请不要传，默认 300 秒"
                    }
                },
                "required": ["command"]
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
                    "route": {"type": "string", "enum": ["local", "mcp"]},
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
            "name": "call_dynamic_tool",
            "description": "代理执行工具。用于调用你通过 fetch_tool 获取到的动态工具。你必须把动态工具的名称和符合其 schema 的参数传给本工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_tool_name": {
                        "type": "string",
                        "description": "要调用的动态工具名称"
                    },
                    "arguments": {
                        "type": "object",
                        "description": "符合该动态工具 schema 的参数对象"
                    }
                },
                "required": ["target_tool_name", "arguments"]
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
            "name": "search_in_system",
            "description": "全局系统搜索工具。根据自然语言描述，同时在系统可用插件工具(Tools)和技能库(Skills)中搜索匹配度最高的能力。不知道怎么做某项任务时，优先用这个全局搜索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "你想要搜索的功能的自然语言描述，例如 '力扣 每日一题' 或 '抓取网页数据'"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "需要为 Tool 和 Skill 各自返回的最高匹配数量，默认返回前 3 个"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_filesystem",
            "description": "列出宿主机文件系统结构（目录树、大小、绝对路径）。遵循 dont_read_dirs 黑名单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "起始路径，默认当前目录"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "递归深度，1=仅当前目录，2=含子目录，以此类推，默认1"
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "是否显示隐藏文件，默认 false"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网内容并返回结构化结果列表（标题、URL、摘要）。优先 Tavily API，降级 DuckDuckGo。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返回结果数量上限，默认 5"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "import_file",
            "description": "将宿主机文件导入沙盒工作区。导入后在沙盒内可用 execute_command 操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "host_path": {
                        "type": "string",
                        "description": "宿主机上文件的绝对路径"
                    },
                    "sandbox_dir": {
                        "type": "string",
                        "description": "沙盒内的目标目录（相对于 /agent_vm/），默认 imports"
                    }
                },
                "required": ["host_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_file",
            "description": "将沙盒内的文件导出到宿主机。目标路径必须在 allowed_export_dirs 内（见 file_config.json）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sandbox_path": {
                        "type": "string",
                        "description": "沙盒内文件路径，如 /agent_vm/imports/result.pdf"
                    },
                    "host_path": {
                        "type": "string",
                        "description": "宿主机目标路径"
                    }
                },
                "required": ["sandbox_path", "host_path"]
            }
        }
    },
]

BASE_TOOL_NAMES = [tool["function"]["name"] for tool in BASE_TOOLS]

class ToolSearcher:
    def __init__(self, jsonl_path: str):
        self.tools = []
        self.corpus = []
        # 加载工具数据
        self._load_tools(jsonl_path)
        # 初始化并拟合 TF-IDF 模型
        self.vectorizer = TfidfVectorizer()
        # 对工具库的文本进行向量化
        if self.corpus:
            self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

    def _load_tools(self, jsonl_path: str):
        """
        读取 jsonl 文件，并将 plugin, func, desc 组合成用于匹配的语料文本。
        """
        if not os.path.exists(jsonl_path):
            return
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tool = json.loads(line)
                    self.tools.append(tool)
                    # 拼接 plugin, func, desc 作为每个工具的文本表征
                    text_representation = f"{tool.get('plugin', '')} {tool.get('func', '')} {tool.get('desc', '')}"
                    self.corpus.append(text_representation)
                except json.JSONDecodeError:
                    continue

    def _process_query(self, query: str) -> str:
        """
        核心处理逻辑：
        1. 对 Query 进行中文分词
        2. 剔除无效符号，对词汇进行英文翻译
        3. 拼接原词和英文翻译，丰富召回特征
        """
        # 1. 使用 jieba 进行分词
        words = jieba.lcut(query)
        processed_tokens = []
        for word in words:
            word = word.strip()
            # 过滤掉单字符的无意义标点
            if len(word) == 0 or word in "，。！？、,!?()（）":
                continue
            # 保留原词
            processed_tokens.append(word)
            # 2. 禁用网络翻译，直接保留原词的小写形式即可
            processed_tokens.append(word.lower())
        # 3. 将处理后的特征词汇拼接成字符串
        expanded_query = " ".join(processed_tokens)
        return expanded_query

    def search(self, query: str, top_k: int = 3) -> list:
        """
        执行搜索并返回匹配度最高的 Top K 个工具
        """
        if not self.corpus:
            return []
        # 对查询语句进行分词和翻译扩展
        expanded_query = self._process_query(query)
        # 将扩展后的查询转换为 TF-IDF 向量
        query_vector = self.vectorizer.transform([expanded_query])
        # 计算查询向量与所有工具向量的余弦相似度
        similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
        # 获取相似度最高的前 k 个索引（从大到小）
        top_k_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in top_k_indices:
            # 只有当相似度大于 0 时才返回
            if similarities[idx] > 0:
                results.append({
                    "score": round(float(similarities[idx]), 4),
                    "tool": self.tools[idx]
                })
        return results





def get_menu(route: str, plugin: str) -> str:
    """获取工具菜单（无异常拦截，直接抛给上层）"""
    if route not in ["local", "mcp"]:
        raise ValueError("无效的路由参数，必须指定两大 route 之一: local 或 mcp")

    if not os.path.exists(TOOL_INDEX_FILE):
        init_tool()
        if not os.path.exists(TOOL_INDEX_FILE):
            raise FileNotFoundError("工具注册表未初始化，找不到 tool.jsonl")

    tools = []
    with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            tool = json.loads(line)
            if tool["route"] == route and tool["plugin"] == plugin:
                tools.append(tool)

    if not tools:
        return _format_response("text", f"当前路由 '{route}' 下插件 '{plugin}' 没有可用的工具。")

    result = f"## 插件工具菜单 (Route: {route}, Plugin: {plugin})\n\n"
    result += "| func | desc |\n"
    result += "|------|------|\n"

    for tool in tools:
        result += f"| {tool['func']} | {tool['desc']} |\n"

    result += f"\n**总计: {len(tools)} 个功能**"
    return _format_response("text", result)


def _load_tool_index() -> list:
    """读取现有的 tool.jsonl，返回所有条目"""
    entries = []
    if os.path.exists(TOOL_INDEX_FILE):
        try:
            with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
    return entries


def _save_tool_index(entries: list):
    """原子写入 tool.jsonl"""
    tmp = TOOL_INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    os.replace(tmp, TOOL_INDEX_FILE)


def _merge_tools(existing: list, new_tools: list) -> list:
    """合并工具列表，按 (route, plugin, func) 去重，已有的跳过"""
    seen = {(e["route"], e["plugin"], e["func"]) for e in existing}
    merged = list(existing)
    for tool in new_tools:
        key = (tool["route"], tool["plugin"], tool["func"])
        if key not in seen:
            merged.append(tool)
            seen.add(key)
    return merged


def init_tool():
    """1. 主线程同步初始化本地工具索引：快速扫描、去重追加"""
    print("🔄 开始扫描本地工具...")

    existing = _load_tool_index()
    new_local = []

    try:
        from src.plugins.plugin_collection.local_manager import init_local_config_data
        if os.path.exists(LOCAL_TOOL_YAML):
            os.remove(LOCAL_TOOL_YAML)
        init_local_config_data()

        if os.path.exists(LOCAL_TOOL_YAML):
            with open(LOCAL_TOOL_YAML, "r", encoding="utf-8") as f:
                local_config = yaml.safe_load(f) or {}
                for plugin_name, plugin_data in local_config.items():
                    functions = plugin_data.get("functions", {})
                    for func_name, func_data in functions.items():
                        desc = func_data.get("function", {}).get("description", "无描述")
                        new_local.append({"route": "local", "plugin": plugin_name, "func": func_name, "desc": desc})
    except Exception as e:
        print(f"❌ 扫描本地工具异常: {e}")

    merged = _merge_tools(existing, new_local)
    _save_tool_index(merged)

    added = len(merged) - len(existing)
    print(f"✅ 本地工具已就绪: 共 {len(merged)} 条 (新增 {added})")
    return merged


def _run_mcp_init():
    """2. 后台线程运行的 MCP 注册逻辑"""
    try:
        from src.utils.config import get_mcp_servers
        configured_servers = set(get_mcp_servers().keys())
        if not configured_servers:
            return

        existing = _load_tool_index()
        indexed_servers = {t["plugin"] for t in existing if t.get("route") == "mcp"}

        missing_servers = configured_servers - indexed_servers
        if not missing_servers:
            print(f"✅ [MCP] 工具已全部在索引中 {configured_servers}，跳过后台连接。")
            return

        print(f"🔌 [MCP] 发现未注册的服务器: {missing_servers}，正在后台连接获取 Schema...")

        from src.plugins.route.mcp_tool import extract_mcp_fingerprints_sync
        mcp_tools = extract_mcp_fingerprints_sync()

        if mcp_tools:
            latest_existing = _load_tool_index()

            merged = _merge_tools(latest_existing, mcp_tools)
            _save_tool_index(merged)

            added = len(merged) - len(latest_existing)
            print(f"✅ [MCP] 后台注册完成: 获取 {len(mcp_tools)} 个工具 (追加了 {added} 个)")
    except Exception as e:
        print(f"❌ [MCP] 后台注册异常: {e}")


def start_mcp_background_init():
    """暴露给外部的启动口：将 MCP 注册扔进 Daemon 线程"""
    import threading
    thread = threading.Thread(target=_run_mcp_init, name="MCP_Init_Thread", daemon=True)
    thread.start()
    return thread

def fetch_tool_schemas(route: str, plugin_name: str, tool_names: list) -> list:
    """批量获取工具 schemas（无异常拦截，直接抛给上层）"""
    schemas = []
    if route == "local":
        load_local_tool_yaml()
        plugin_config = CONFIG_DATA.get(plugin_name, {})
        funcs = plugin_config.get("functions", {})
        for tool_name in tool_names:
            func_config = funcs.get(tool_name)
            if func_config and "function" in func_config:
                schemas.append({"type": "function", "function": func_config["function"]})
    elif route == "mcp":
        from src.plugins.route.mcp_tool import get_mcp_tool_schemas_sync
        schemas = get_mcp_tool_schemas_sync(plugin_name, tool_names)
    return schemas if schemas else []


def handle_fetch_tool(arguments: dict) -> str:
    fetch_route = arguments.get("route")
    p_name = arguments.get("plugin_name")
    t_names = arguments.get("tool_names", [])
    if not t_names and "tool_name" in arguments:
        t_names = [arguments.get("tool_name")]

    success_tools = []
    failed_tools = []

    fetched_schemas = fetch_tool_schemas(fetch_route, p_name, t_names)
    fetched_dict = {s["function"]["name"]: s for s in fetched_schemas}

    for t_name in t_names:
        if t_name in fetched_dict:
            schema_dict = fetched_dict[t_name]
            real_func_name = schema_dict["function"]["name"]
            if real_func_name in BASE_TOOL_NAMES:
                failed_tools.append(f"{t_name}(保留关键字被拒绝)")
            else:
                success_tools.append(t_name)
        else:
            failed_tools.append(t_name)

    res_messages = []
    if success_tools:
        res_messages.append(f"✅ 成功加载工具: {', '.join(success_tools)}。")
        res_messages.append("⚠️ 注意：这些工具不在你的原生能力列表中，你必须使用 `call_dynamic_tool` 工具，将工具名和参数传给它来进行代理调用！")
        res_messages.append("--- 以下是获取到的动态工具 Schema ---")
        for t_name in success_tools:
            schema_item = fetched_dict[t_name]
            res_messages.append(json.dumps(schema_item["function"], ensure_ascii=False))
        res_messages.append("-----")

    if failed_tools:
        res_messages.append(f"❌ 以下工具找不到或加载失败: {', '.join(failed_tools)}")

    return _format_response("text", "\n".join(res_messages))


DEFAULT_SKILL_PATH = Path("data/skill")


class SkillSearcher:
    def __init__(self, skill_dir: Path):
        self.skills = []
        self.corpus = []
        # 加载技能数据
        self._load_skills(skill_dir)
        # 初始化并拟合 TF-IDF 模型
        self.vectorizer = TfidfVectorizer()
        if  self.corpus:
            self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

    def _load_skills(self, skill_dir: Path):
        """
        遍历 Skill 目录，解析 SKILL.md，并将 name, description 和 content 组合成用于匹配的语料文本。
        """
        if not skill_dir.exists() or not  skill_dir.is_dir():
            return
        for item in  skill_dir.iterdir():
            if  item.is_dir():
                md_file = item / "SKILL.md"
                if  md_file.exists():
                    parsed_data = _parse_skill_md(md_file)
                    metadata = parsed_data["metadata" ]
                    name = metadata.get("name" , item.name)
                    desc = metadata.get("description", metadata.get("desc", "" ))
                    content = parsed_data.get("content", "" )
                    
                    self.skills.append({
                        "name" : name,
                        "description" : desc,
                        "dir_name" : item.name
                    })
                    # 拼接元数据和内容作为文本表征
                    text_representation = f"{name} {desc} {content}"
                    self.corpus.append(text_representation)

    def _process_query(self, query: str) -> str:
        """
        核心处理逻辑：
        分词 -> 直接保留小写形式
        """
        words = jieba.lcut(query)
        processed_tokens = []
        for word in words:
            word = word.strip()
            if len(word) == 0 or word in "，。！？、,!?()（）":
                continue
            processed_tokens.append(word.lower())
        return " ".join(processed_tokens)

    def search(self, query: str, top_k: int = 3) -> list:
        """执行搜索并返回匹配度最高的前 K 个技能"""
        if not  self.corpus:
            return  []
        expanded_query = self._process_query(query)
        query_vector = self.vectorizer.transform([expanded_query])
        similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
        top_k_indices = np.argsort(similarities)[::-1 ][:top_k]
        
        results = []
        for idx in  top_k_indices:
            if similarities[idx] > 0 :
                results.append({
                    "score": round(float(similarities[idx]), 4 ),
                    "skill" : self.skills[idx]
                })
        return  results

def search_in_system(query: str, top_k: int = 3) -> str:
    """全局统一搜索接口，同时搜索可用工具与技能"""
    result_text = f"🎯 针对查询 '{query}' 的全局搜索结果 (Top {top_k}):\n\n"
    
    # 1. 搜索 Tools
    tool_results_text = "【🔌 插件工具 (Tools)】\n"
    if not os.path.exists(TOOL_INDEX_FILE):
        init_tool()
        
    if not os.path.exists(TOOL_INDEX_FILE):
        tool_results_text += "⚠️ 工具注册表未初始化，找不到 tool.jsonl\n"
    else:
        tool_searcher = ToolSearcher(TOOL_INDEX_FILE)
        t_results = tool_searcher.search(query, top_k)
        if not t_results:
            tool_results_text += "未找到匹配度较高的可用工具。\n"
        else:
            tool_results_text += "| 路由 (route) | 插件 (plugin) | 功能名 (func) | 匹配得分 | 描述 |\n"
            tool_results_text += "|-------------|---------------|---------------|---------|------|\n"
            for res in t_results:
                t = res["tool"]
                tool_results_text += f"| {t.get('route', 'unknown')} | {t.get('plugin', 'unknown')} | {t.get('func', 'unknown')} | {res['score']} | {t.get('desc', '无描述')} |\n"

    # 2. 搜索 Skills
    skill_results_text = "\n【🧰 技能经验 (Skills)】\n"
    try:
        skill_searcher = SkillSearcher(DEFAULT_SKILL_PATH)
        s_results = skill_searcher.search(query, top_k)
        if not s_results:
            skill_results_text += "未找到匹配度较高的可用 Skill。\n"
        else:
            skill_results_text += "| 技能名称 (Name) | 匹配得分 | 描述 (Desc) |\n"
            skill_results_text += "|-----------------|---------|-------------|\n"
            for res in s_results:
                s = res["skill"]
                skill_results_text += f"| {s.get('name', 'unknown')} | {res['score']} | {s.get('description', '无描述')} |\n"
    except Exception as e:
        skill_results_text += f"⚠️ Skill搜索异常: {e}\n"

    result_text += tool_results_text
    result_text += skill_results_text
    result_text += "\n💡 提示：\n1. 对于工具，你可以使用 fetch_tool 获取 Schema 后用 call_dynamic_tool 调用。\n2. 对于技能，你可以使用 load_skill(name='技能名称') 获取详情及执行指南。"
    
    return _format_response("text", result_text)


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
    return {"metadata": metadata, "content": content}


def load_skill(name: str):
    """加载技能文件（无异常拦截，直接抛给上层）"""
    skill_path = DEFAULT_SKILL_PATH
    base_dir = Path(skill_path)
    target_dir = base_dir / name
    md_file = target_dir / "SKILL.md"
    if not target_dir.is_dir() or not md_file.exists():
        for item in base_dir.iterdir():
            if item.is_dir():
                item_md_file = item / "SKILL.md"
                if item_md_file.exists():
                    parsed_data = _parse_skill_md(item_md_file)
                    if parsed_data["metadata"].get("name", item.name) == name:
                        target_dir = item
                        md_file = item_md_file
                        break
    if not target_dir.is_dir() or not md_file.exists():
        raise FileNotFoundError(f"Skill '{name}' not exist")
    parsed_data = _parse_skill_md(md_file)
    metadata = parsed_data["metadata"]
    skill_name = metadata.get("name", target_dir.name)
    desc = metadata.get("description", metadata.get("desc", ""))
    host_path = f"data/skill/{target_dir.name}"
    sandbox_path = f"/agent_vm/skill/{target_dir.name}"
    result = (
        f"🎯 技能名称 (Name): {skill_name}\n"
        f"📝 技能描述 (Desc): {desc}\n"
        f"📂 宿主机存放路径 (Host): {host_path}\n"
        f"🐳 沙盒执行路径 (Sandbox): {sandbox_path}\n"
        f"=========================================\n"
        f"⚠️ 执行指引 (Execution Guide):\n"
        f"请注意，当你使用 `execute_command` 运行此技能的脚本时：\n"
        f"1. 你的默认执行环境是安全的 Docker 沙盒。\n"
        f"2. 务必以沙盒路径 `{sandbox_path}` 作为起始工作目录 (使用 `cd` 切换或直接使用该绝对路径)。\n"
        f"3. 严禁在执行命令时混用宿主机的 `data/skill/` 路径，否则会导致找不到文件。\n"
        f"=========================================\n"
        f"📄 技能详情 (Content):\n{parsed_data['content']}"
    )
    return _format_response("text", result)


def list_skill(page: int = 1, size: int = 20) -> str:
    """列举所有技能（无异常拦截，直接抛给上层）"""
    base_dir = Path(DEFAULT_SKILL_PATH)
    if not base_dir.exists() or not base_dir.is_dir():
        raise FileNotFoundError("Skill 目录不存在，未找到任何 Skill。")

    found_skills = []
    for item in base_dir.iterdir():
        if item.is_dir():
            md_file = item / "SKILL.md"
            if md_file.exists():
                parsed_data = _parse_skill_md(md_file)
                found_skills.append({
                    "name": parsed_data["metadata"].get("name", item.name),
                    "description": parsed_data["metadata"].get("description", parsed_data["metadata"].get("desc", "暂无描述")),
                    "dir_name": item.name
                })

    if not found_skills:
        raise FileNotFoundError("当前目录下没有找到包含 SKILL.md 的有效 Skill。")

    found_skills.sort(key=lambda x: x["dir_name"])
    total_skills = len(found_skills)
    total_pages = (total_skills + size - 1) // size
    page = max(1, min(page, max(1, total_pages)))

    paged_skills = found_skills[(page - 1) * size: page * size]
    result = f"【可用 Skill 总览】共 {total_skills} 个，当前第 {page}/{total_pages} 页：\n"
    for skill in paged_skills:
        result += f"\n👉 Skill: {skill['name']}\n   📝 描述: {skill['description']}\n"
    result += "\n💡 提示：使用 load_skill(name='skill_name') 获取完整内容与执行指南。"
    if page < total_pages:
        result += f"\n➡️ 翻页提示：当前页已满，请调用 list_skill(page={page + 1}) 查看下一页。"

    return _format_response("text", result)


if sys.platform == 'win32':
    from pexpect.popen_spawn import PopenSpawn

    SpawnClass = PopenSpawn
    DOCKER_EXEC_CMD = "docker exec -i {container_name} /bin/bash"

    def check_alive(p):
        if p is None: return False
        return p.proc.poll() is None

    def force_close(p):
        if p is None: return
        try:
            import signal
            p.kill(signal.SIGTERM)
        except Exception:
            pass
else:
    SpawnClass = pexpect.spawn
    DOCKER_EXEC_CMD = "docker exec -it {container_name} /bin/bash"

    def check_alive(p):
        if p is None: return False
        return p.isalive()

    def force_close(p):
        if p is None: return
        p.close(force=True)

_docker_manager_instance: Optional['DockerManager'] = None


def _get_docker_env() -> dict:
    """从配置读取 Docker 代理环境变量（只返回非空值）"""
    try:
        from src.utils.config import get_docker_config
        cfg = get_docker_config()
        env = {}
        if cfg.get("http_proxy"):
            env["HTTP_PROXY"] = cfg["http_proxy"]
        if cfg.get("https_proxy"):
            env["HTTPS_PROXY"] = cfg["https_proxy"]
        if cfg.get("all_proxy"):
            env["ALL_PROXY"] = cfg["all_proxy"]
        return env
    except Exception:
        return {}


class DockerManager:
    def __init__(self, image: str, container_name: str = "agent_computer", workspace_dir: str | None = None):
        if not image: raise ValueError("A Docker image must be provided.")
        self.client = docker.from_env()
        self.image = image
        self.container_name = container_name
        self.workspace_dir = workspace_dir
        self.container_workspace = "/agent_vm"
        self.container = None
        self.shell_pool = {}
        self.pool_lock = threading.Lock()

    def start(self):
        try:
            self.container = self.client.containers.get(self.container_name)
            if self.container.status != "running":
                self.container.start()
        except NotFound:
            run_kwargs = {
                "name": self.container_name,
                "command": "sleep infinity",
                "detach": True,
                "working_dir": self.container_workspace,
                "environment": _get_docker_env()
            }
            volumes = {}
            if self.workspace_dir is not None:
                os.makedirs(self.workspace_dir, exist_ok=True)
                volumes[os.path.abspath(self.workspace_dir)] = {"bind": self.container_workspace, "mode": "rw"}

            skill_host_dir = os.path.abspath("./data/skill")
            os.makedirs(skill_host_dir, exist_ok=True)
            volumes[skill_host_dir] = {"bind": f"{self.container_workspace}/skill", "mode": "rw"}

            from src.utils.config import get_filesystem_config
            docker_mount = get_filesystem_config().get("docker_mount", [])
            for dirpath in docker_mount:
                new_host_dir = os.path.abspath(dirpath)
                os.makedirs(new_host_dir, exist_ok=True)
                target_name = os.path.basename(os.path.normpath(dirpath))
                container_bind_path = f"{self.container_workspace}/{target_name}"
                volumes[new_host_dir] = {"bind": container_bind_path, "mode": "rw"}

            run_kwargs["volumes"] = volumes
            self.container = self.client.containers.run(self.image, **run_kwargs)
        except DockerException as e:
            raise RuntimeError(f"Docker API error: {e}")

    def stop(self):
        with self.pool_lock:
            active_session_ids = list(self.shell_pool.keys())
        for sid in active_session_ids:
            self.close_shell(sid)
        if self.container:
            try:
                print(f"🛑 正在关闭并清理 Docker 沙盒 ({self.container_name})...")
                self.container.stop(timeout=2)
                print("✅ 沙盒已成功关闭。")
            except Exception as e:
                print(f"⚠️ 关闭沙盒容器失败: {e}")
        self.container = None

    def _ensure_shell(self, session_id: str):
        if not self.container: raise RuntimeError("Container not running.")
        with self.pool_lock:
            if session_id in self.shell_pool: return
            print(f"[+] Auto-creating new shell session: '{session_id}'")
            command = DOCKER_EXEC_CMD.format(container_name=self.container.name)
            try:
                shell_process = SpawnClass(command, encoding="utf-8", timeout=120)
                shell_process.sendline("stty -echo\nexport PS1=''\nexport TERM=dumb\necho '__SHELL_READY__'\n")
                shell_process.expect("__SHELL_READY__", timeout=10)
                self.shell_pool[session_id] = {"process": shell_process, "lock": threading.Lock()}
            except pexpect.exceptions.TIMEOUT:
                raise RuntimeError("Timeout initializing shell environment.")

    def close_shell(self, session_id: str):
        with self.pool_lock:
            session = self.shell_pool.pop(session_id, None)
        if session:
            with session["lock"]:
                process = session["process"]
                if check_alive(process): force_close(process)
            print(f"[-] Shell session closed: {session_id}")

    def _restart_shell(self, session_id: str):
        session = self.shell_pool.get(session_id)
        if not session: return
        if check_alive(session["process"]): force_close(session["process"])
        command = DOCKER_EXEC_CMD.format(container_name=self.container.name)
        new_process = SpawnClass(command, encoding="utf-8", timeout=120)
        new_process.sendline("stty -echo\nexport PS1=''\nexport TERM=dumb\necho '__SHELL_READY__'\n")
        new_process.expect("__SHELL_READY__", timeout=10)
        session["process"] = new_process

    def execute(self, session_id: str, command: str, timeout: int = 300) -> tuple[int, str, str]:
        self._ensure_shell(session_id)
        with self.pool_lock:
            session = self.shell_pool[session_id]

        with session["lock"]:
            process = session["process"]
            if not check_alive(process):
                print(f"[yellow]Shell '{session_id}' died. Restarting...[/yellow]")
                self._restart_shell(session_id)
                process = session["process"]

            marker_id = uuid.uuid4().hex
            marker_str = f"__CMD_DONE_{marker_id}__"
            full_payload = f"{command.strip()}\necho -e \"\\n{marker_str}$?|$(pwd)\""

            process.sendline(full_payload)
            try:
                process.expect(f"{marker_str}(\\d+)\\|(.*)", timeout=timeout)
            except pexpect.exceptions.TIMEOUT:
                partial_output = self._clean_ansi(process.before or "")
                print(f"[red]⚠️ Shell '{session_id}' timed out. Resetting...[/red]")
                self._restart_shell(session_id)
                return -1, f"⚠️ Command timed out.\nPartial Output:\n{partial_output.strip()}", "unknown"

            exit_code = int(process.match.group(1))
            cwd = process.match.group(2).strip()
            cleaned_output = self._clean_ansi(process.before).strip()
            lines = [line for line in cleaned_output.splitlines() if line.strip() != command.strip()]
            final_output = "\n".join(lines).strip()
            # ✅ 删除字数限制逻辑，直接返回完整输出
            return exit_code, final_output, cwd

    def _clean_ansi(self, text: str) -> str:
        return re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', text)


def _get_manager() -> 'DockerManager':
    global _docker_manager_instance
    if _docker_manager_instance is None:
        _docker_manager_instance = DockerManager(
            image="my_agent_env:latest",
            workspace_dir="./agent_vm"
        )
        atexit.register(_docker_manager_instance.stop)
    try:
        _docker_manager_instance.start()
    except Exception as e:
        raise RuntimeError(f"Docker 容器唤醒失败: {str(e)}")
    return _docker_manager_instance


def execute_command(command: str, session_id: str = "default", timeout: int = 300) -> str:
    """
    执行 Shell 命令（无异常拦截，直接抛给上层）
    """
    manager = _get_manager()
    exit_code, output, cwd = manager.execute(session_id, command, timeout)
    result = {"session_id": session_id, "exit_code": exit_code, "output": output, "cwd": cwd}
    return _format_response("warning" if exit_code != 0 else "text", result)


def close_shell(session_id: str = "default") -> str:
    """
    关闭 Shell 会话（无异常拦截，直接抛给上层）
    """
    _get_manager().close_shell(session_id)
    return _format_response("text", f"Shell session '{session_id}' successfully closed.")


# ==========================================
# 统一调度出口 (Call Base Tool)
# ==========================================



def list_filesystem(path: str = ".", depth: int = 1, show_hidden: bool = False) -> str:
    """列出宿主机文件系统结构（带大小、绝对路径），遵循 dont_read_dirs 黑名单
    
    Args:
        path: 起始路径，默认当前目录
        depth: 递归深度，1=仅当前目录，2=子目录，以此类推
        show_hidden: 是否显示隐藏文件/目录
    
    Returns: 格式化的目录树
    """
    import os, json, time
    
    root = os.path.abspath(path)
    if not os.path.exists(root):
        raise FileNotFoundError(f"路径不存在: {root}")
    
    # 加载黑名单
    from src.utils.config import get_filesystem_config
    dont_read = [os.path.abspath(d) for d in get_filesystem_config().get("dont_read_dirs", [])]
    
    def _check_allowed(p: str) -> bool:
        for denied in dont_read:
            if p.startswith(denied):
                return False
        return True
    
    if not _check_allowed(root):
        raise PermissionError(f"路径在黑名单中，不可读取: {root}")
    
    lines = []
    total_size = 0
    file_count = 0
    dir_count = 0
    
    def _walk(current: str, prefix: str, remaining_depth: int):
        nonlocal total_size, file_count, dir_count
        
        if not _check_allowed(current):
            lines.append(f"{prefix}[黑名单，已跳过]")
            return
        
        try:
            entries = sorted(os.listdir(current))
        except PermissionError:
            lines.append(f"{prefix}[权限不足]")
            return
        
        for i, entry in enumerate(entries):
            if not show_hidden and entry.startswith("."):
                continue
            
            full_path = os.path.join(current, entry)
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            
            try:
                stat = os.stat(full_path)
                is_dir = os.path.isdir(full_path)
                size = stat.st_size
                mtime = time.strftime("%m-%d %H:%M", time.localtime(stat.st_mtime))
                
                if is_dir:
                    dir_count += 1
                    size_str = ""
                    lines.append(f"{prefix}{connector}{entry}/  ({mtime})")
                    if remaining_depth > 1:
                        ext = "    " if is_last else "│   "
                        _walk(full_path, prefix + ext, remaining_depth - 1)
                else:
                    file_count += 1
                    total_size += size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024 * 1024:
                        size_str = f"{size/1024:.1f}KB"
                    else:
                        size_str = f"{size/1024/1024:.1f}MB"
                    lines.append(f"{prefix}{connector}{entry}  ({size_str}, {mtime})")
            except (OSError, PermissionError):
                lines.append(f"{prefix}{connector}{entry}  [不可访问]")
    
    # 根目录信息
    root_stat = os.stat(root)
    root_mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(root_stat.st_mtime))
    lines.append(f"{root}  ({root_mtime})")
    
    _walk(root, "", depth + 1)
    
    summary = (f"\n📁 {dir_count} 个目录, 📄 {file_count} 个文件, "
               f"总计 {total_size/1024/1024:.1f}MB")
    lines.append(summary)
    
    return _format_response("text", {
        "path": root,
        "tree": "\n".join(lines),
        "dir_count": dir_count,
        "file_count": file_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1024 / 1024, 1),
    })


def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网内容并返回结构化结果
    
    优先使用 Tavily API（需配置 web_api.tavily_api_key），
    无可用 API 时降级到 DuckDuckGo。
    """
    import json, os, requests
    
    results = []
    error_logs = []
    
    # 优先级 1: Tavily API
    from src.utils.config import get_web_api_config
    tavily_key = get_web_api_config().get("tavily_api_key", "")
    if tavily_key:
        try:
            data = {"api_key": tavily_key, "query": query, "search_depth": "basic", "max_results": max_results}
            resp = requests.post("https://api.tavily.com/search", json=data, timeout=10)
            if resp.status_code == 200:
                for res in resp.json().get("results", []):
                    results.append({"title": res["title"], "url": res["url"], "snippet": res["content"]})
            else:
                error_logs.append(f"Tavily API Error: {resp.status_code}")
        except Exception as e:
            error_logs.append(f"Tavily Exception: {str(e)}")
    
    # 优先级 2: DuckDuckGo (no API key needed)
    if not results:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")})
        except ImportError:
            error_logs.append("DuckDuckGo not available (install duckduckgo_search)")
        except Exception as e:
            error_logs.append(f"DDGS Exception: {str(e)}")
    
    if not results:
        return _format_response("error", f"所有搜索源均失败: {', '.join(error_logs)}")
    
    md = f"# Search Results for: {query}\n\n"
    for i, res in enumerate(results, 1):
        md += f"### {i}. {res['title']}\n- URL: {res['url']}\n- {res['snippet'][:500]}\n\n"
    
    return _format_response("text", {
        "query": query,
        "results_count": len(results),
        "markdown": md,
        "results": results,
    })

def import_file(host_path: str, sandbox_dir: str = "imports") -> str:
    """将宿主机文件/目录导入沙盒工作区
    
    安全检查：
    - 禁止导入 dont_read_dirs 内的文件
    - 导入上级目录时，黑名单内的子文件/子目录自动跳过
    - 目录导入有 30MB 总大小限制
    """
    import shutil, os, json
    
    host_path = os.path.abspath(host_path)
    if not os.path.exists(host_path):
        raise FileNotFoundError(f"宿主机路径不存在: {host_path}")
    
    # 加载 dont_read_dirs 黑名单
    from src.utils.config import get_filesystem_config
    dont_read = [os.path.abspath(d) for d in get_filesystem_config().get("dont_read_dirs", [])]
    
    def _is_denied(p: str) -> bool:
        p = os.path.abspath(p)
        for denied in dont_read:
            if p == denied or p.startswith(denied + os.sep):
                return True
        return False
    
    # 根路径检查
    if _is_denied(host_path):
        raise PermissionError(
            f"禁止导入黑名单内的路径: {host_path}\n"
            f"黑名单: {dont_read}"
        )
    
    # 检查上级目录内是否包含黑名单路径（导入父目录时警告但不阻止，自动跳过）
    skipped_dirs = []
    skipped_files = 0
    
    mount_point = os.path.abspath("./agent_vm")
    sandbox_subdir = sandbox_dir.strip("/")
    dest_dir = os.path.join(mount_point, sandbox_subdir)
    os.makedirs(dest_dir, exist_ok=True)
    
    MAX_SIZE = 30 * 1024 * 1024  # 30MB
    
    if os.path.isfile(host_path):
        # 单文件导入
        fname = os.path.basename(host_path)
        file_size = os.path.getsize(host_path)
        if file_size > MAX_SIZE:
            raise ValueError(f"文件过大 ({file_size / 1024 / 1024:.1f}MB)，超过 30MB 限制: {host_path}")
        shutil.copy2(host_path, os.path.join(dest_dir, fname))
        sandbox_path = f"/agent_vm/{sandbox_subdir}/{fname}"
        msg = f"文件已导入沙盒: {sandbox_path} ({file_size / 1024:.1f}KB)"
    
    elif os.path.isdir(host_path):
        # 目录导入：先走一遍计算总大小 + 检查黑名单
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(host_path):
            # 检查当前目录是否在黑名单内
            if _is_denied(dirpath):
                skipped_dirs.append(dirpath)
                dirnames.clear()  # 不进入子目录
                filenames.clear()  # 不处理文件
                continue
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                if _is_denied(fp):
                    skipped_files += 1
                    continue
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    pass
                if total_size > MAX_SIZE:
                    raise ValueError(
                        f"目录过大 (超过 30MB)，禁止导入: {host_path}\n"
                        f"请只导入需要的文件"
                    )
        
        # 正式复制，同样跳过黑名单
        def _ignore_denied(src, names):
            ignored = set()
            for name in names:
                full = os.path.join(src, name)
                if _is_denied(full):
                    ignored.add(name)
            return ignored
        
        dirname = os.path.basename(host_path.rstrip("/\\"))
        dest_path = os.path.join(dest_dir, dirname)
        if os.path.exists(dest_path):
            import time
            dest_path = os.path.join(dest_dir, f"{dirname}_{int(time.time())}")
        shutil.copytree(host_path, dest_path, symlinks=False, ignore=_ignore_denied)
        sandbox_path = f"/agent_vm/{sandbox_subdir}/{os.path.basename(dest_path)}"
        
        msg = f"目录已导入沙盒: {sandbox_path} ({total_size / 1024 / 1024:.1f}MB)"
        if skipped_dirs:
            msg += f"\n⚠️ 已跳过 {len(skipped_dirs)} 个黑名单目录: {skipped_dirs}"
        if skipped_files:
            msg += f"\n⚠️ 已跳过 {skipped_files} 个黑名单文件"
    
    else:
        raise ValueError(f"不支持的路径类型: {host_path}")
    
    return _format_response("text", {
        "sandbox_path": sandbox_path,
        "host_path": host_path,
        "message": msg
    })
def export_file(sandbox_path: str, host_path: str) -> str:
    """将沙盒内文件/目录导出到宿主机（带安全检查 + Git 快照）
    
    安全机制：
    - 只允许导出到 allowed_export_dirs
    - 导出前自动创建 Git 快照（init + add + commit）
    - 本地无 git 工具则拒绝导出
    """
    import shutil, os, json, subprocess
    
    sandbox_path = sandbox_path.strip()
    if not sandbox_path.startswith("/agent_vm/"):
        raise PermissionError(f"禁止导出沙盒外的文件: {sandbox_path}")
    
    rel_path = os.path.relpath(sandbox_path, "/agent_vm")
    mount_point = os.path.abspath("./agent_vm")
    host_src = os.path.abspath(os.path.join(mount_point, rel_path))
    
    if not os.path.exists(host_src):
        raise FileNotFoundError(f"沙盒文件/目录不存在: {sandbox_path}")
    
    host_path = os.path.abspath(host_path)
    from src.utils.config import get_filesystem_config
    allowed = [os.path.abspath(d) for d in get_filesystem_config().get("allowed_export_dirs", [])]
    
    if not any(host_path.startswith(d) for d in allowed):
        raise PermissionError(
            f"导出目标不在允许目录内: {host_path}\n"
            f"允许的目录: {allowed}\n"
            f"请在 ~/.purrcat.toml 的 [filesystem] 节中添加"
        )
    
    # 检查 git 是否可用
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        raise RuntimeError(
            "本地未安装 git 工具，禁止导出以保护文件安全。\n"
            "请安装 git 后重试，或手动复制文件。"
        )
    
    # 写入目标文件
    os.makedirs(os.path.dirname(host_path), exist_ok=True)
    if os.path.isfile(host_src):
        shutil.copy2(host_src, host_path)
    elif os.path.isdir(host_src):
        dest = host_path
        if os.path.exists(dest):
            import time
            dest = f"{host_path}_{int(time.time())}"
        shutil.copytree(host_src, dest, symlinks=False)
        host_path = dest
    
    # Git 快照：在目标目录所在的 git 仓库中做 commit
    target_dir = host_path if os.path.isdir(host_path) else os.path.dirname(host_path)
    git_dir = _find_git_root(target_dir)
    
    if git_dir:
        repo_name = os.path.basename(git_dir)
        subprocess.run(["git", "-C", git_dir, "add", "-A"], capture_output=True, timeout=30)
        result = subprocess.run(
            ["git", "-C", git_dir, "commit", "-m", f"auto-snapshot: export {os.path.basename(host_path)}"],
            capture_output=True, timeout=30, text=True
        )
        commit_msg = result.stdout.strip() or result.stderr.strip()
    else:
        # 没有 git 仓库，初始化一个新仓库
        subprocess.run(["git", "-C", target_dir, "init"], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", target_dir, "add", "-A"], capture_output=True, timeout=30)
        result = subprocess.run(
            ["git", "-C", target_dir, "commit", "-m", f"auto-snapshot: initial commit after export"],
            capture_output=True, timeout=30, text=True
        )
        commit_msg = result.stdout.strip() or result.stderr.strip()
        git_dir = target_dir
    
    return _format_response("text", {
        "host_path": host_path,
        "sandbox_path": sandbox_path,
        "git_repo": git_dir,
        "git_commit": commit_msg[:200] if commit_msg else "",
        "message": f"文件已导出到宿主机: {host_path}\n"
                   f"Git 快照已记录 ({git_dir})"
    })


def _find_git_root(path: str) -> str:
    """向上查找最近的 .git 目录"""
    import subprocess, os
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, timeout=10, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    # 手动向上查找
    current = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent

def call_base_tool(tool_name: str, arguments: dict) -> str:
    """
    统一调度 base_tool 模块下的工具
    【已脱壳】不做任何异常拦截，直接抛给上层 parse_tool
    返回: 格式化后的 JSON 字符串
    """
    result_content = ""

    if tool_name == "search_in_system":
        result_content = search_in_system(arguments.get("query"), arguments.get("top_k", 3))
    elif tool_name == "execute_command":
        result_content = execute_command(**arguments)
    elif tool_name == "fetch_tool":
        result_content = handle_fetch_tool(arguments)
    elif tool_name == "load_skill":
        result_content = load_skill(arguments.get("name"))
    elif tool_name == "close_shell":
        result_content = close_shell(arguments.get("session_id", "default"))
    elif tool_name == "list_filesystem":
        result_content = list_filesystem(
            arguments.get("path", "."),
            arguments.get("depth", 1),
            arguments.get("show_hidden", False)
        )
    elif tool_name == "web_search":
        result_content = web_search(arguments.get("query"), arguments.get("max_results", 5))
    elif tool_name == "import_file":
        result_content = import_file(arguments.get("host_path"), arguments.get("sandbox_dir", "imports"))
    elif tool_name == "export_file":
        result_content = export_file(arguments.get("sandbox_path"), arguments.get("host_path"))
    elif tool_name == "call_dynamic_tool":
        result_content = _format_response("error", "❌ 系统错误：call_dynamic_tool 参数异常。请勿直接调用此工具，应该在 fetch_tool 获取 Schema 后由系统自动代理调用。")
    else:
        raise ValueError(f"未知的基础工具: {tool_name}")

    return result_content