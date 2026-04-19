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
from deep_translator import GoogleTranslator
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
            "name": "get_menu",
            "description": "获取指定插件下所有功能(func)及其描述(desc)的菜单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {"type": "string", "enum": ["local", "mcp"],
                              "description": "路由类型，必须指定 local 或 mcp"},
                    "plugin": {"type": "string", "description": "插件名称"}
                },
                "required": ["route", "plugin"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_tool",
            "description": "根据自然语言描述，使用语义和关键词搜索匹配度最高的工具/插件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "你想要搜索的工具功能的自然语言描述，例如 '帮我获取昨天力扣的每日一题'"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "需要返回的最高匹配工具数量，默认返回前 3 个"
                    }
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
                        "type": "string",
                        "description": "符合该动态工具 schema 的完整 JSON 字符串格式参数"
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

BASE_TOOL_NAMES = [tool["function"]["name"] for tool in BASE_TOOLS]

class ToolSearcher:
    def __init__(self, jsonl_path: str):
        self.tools = []
        self.corpus = []
        self.translator = GoogleTranslator(source='zh-CN', target='en')
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
            # 2. 对词汇进行翻译
            # 为了避免把已经是英文的词也翻译一遍，可以加个简单的判断
            if any('\u4e00' <= char <= '\u9fff' for char in word):
                try:
                    translated_word = self.translator.translate(word)
                    if translated_word:
                        processed_tokens.append(translated_word.lower())
                except Exception as e:
                    print(f"翻译 '{word}' 时出错: {e}")
            else:
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


def search_tool(query: str, top_k: int = 3) -> str:
    """工具搜索接口，提供给大模型调用"""
    if not os.path.exists(TOOL_INDEX_FILE):
        init_tool()
        if not os.path.exists(TOOL_INDEX_FILE):
            return _format_response("error", "工具注册表未初始化，找不到 tool.jsonl")
    searcher = ToolSearcher(TOOL_INDEX_FILE)
    results = searcher.search(query, top_k)
    if not results:
        return _format_response("text",
                                f"未找到与 '{query}' 匹配度较高的可用工具。您可以尝试使用 search_tool 搜索或使用 get_menu 获取指定插件的工具清单。")
    result_text = f"🎯 针对查询 '{query}' 的搜索结果 (Top {top_k}):\n\n"
    result_text += "| 路由 (route) | 插件 (plugin) | 功能名 (func) | 匹配得分 | 描述 |\n"
    result_text += "|-------------|---------------|---------------|---------|------|\n"
    for res in results:
        tool = res["tool"]
        route = tool.get("route", "unknown")
        plugin = tool.get("plugin", "unknown")
        func = tool.get("func", "unknown")
        desc = tool.get("desc", "无描述")
        score = res["score"]
        result_text += f"| {route} | {plugin} | {func} | {score} | {desc} |\n"
    result_text += "\n💡 提示：你可以使用 fetch_tool 获取上述列表中的工具 Schema，然后使用 call_dynamic_tool 进行调用。"
    return _format_response("text", result_text)


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


def init_tool():
    """初始化工具索引，每次重启都强制重新生成"""
    print("🔄 开始初始化工具索引...")
    tools_index = []

    try:
        print("📦 处理本地工具...")
        from src.plugins.plugin_collection.local_manager import init_local_config_data
        if os.path.exists(LOCAL_TOOL_YAML):
            os.remove(LOCAL_TOOL_YAML)
            print("🗑️ 已删除本地工具缓存")

        init_local_config_data()

        if os.path.exists(LOCAL_TOOL_YAML):
            with open(LOCAL_TOOL_YAML, "r", encoding="utf-8") as f:
                local_config = yaml.safe_load(f) or {}
                local_count = 0
                for plugin_name, plugin_data in local_config.items():
                    functions = plugin_data.get("functions", {})
                    for func_name, func_data in functions.items():
                        desc = func_data.get("function", {}).get("description", "无描述")
                        tools_index.append({"route": "local", "plugin": plugin_name, "func": func_name, "desc": desc})
                        local_count += 1
                print(f"✅ 本地工具: {local_count} 个")
    except Exception as e:
        print(f"❌ 初始化本地工具异常: {e}")

    try:
        with open(TOOL_INDEX_FILE, "w", encoding="utf-8") as f:
            for tool_info in tools_index:
                f.write(json.dumps(tool_info, ensure_ascii=False) + "\n")
        print(f"✅ 本地工具索引已生成: {TOOL_INDEX_FILE}")
    except Exception as e:
        print(f"❌ 写入工具索引异常: {e}")

    return tools_index


def _init_tool_async():
    """后台异步初始化 MCP 工具索引"""
    import threading
    import asyncio

    def _run_mcp_init():
        try:
            from src.plugins.route.mcp_tool import extract_mcp_fingerprints_sync
            print("🔌 [后台] 开始处理MCP工具...")
            mcp_tools = extract_mcp_fingerprints_sync()

            if mcp_tools:
                existing_tools = []
                if os.path.exists(TOOL_INDEX_FILE):
                    with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            tool = json.loads(line)
                            if tool.get("route") == "local":
                                existing_tools.append(tool)

                with open(TOOL_INDEX_FILE, "w", encoding="utf-8") as f:
                    for tool_info in existing_tools:
                        f.write(json.dumps(tool_info, ensure_ascii=False) + "\n")
                    for tool_info in mcp_tools:
                        f.write(json.dumps(tool_info, ensure_ascii=False) + "\n")
                print(f"✅ [后台] MCP工具索引已更新: {len(mcp_tools)} 个")
            else:
                print("⚠️ [后台] 未发现可用的MCP工具")
        except Exception as e:
            print(f"❌ [后台] 扫描MCP工具异常: {e}")

    thread = threading.Thread(target=_run_mcp_init, daemon=True)
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
        res_messages.append("--------------------------------------")

    if failed_tools:
        res_messages.append(f"❌ 以下工具找不到或加载失败: {', '.join(failed_tools)}")

    return _format_response("text", "\n".join(res_messages))


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
                "environment": {
                    "HTTP_PROXY": "http://host.docker.internal:7897",
                    "HTTPS_PROXY": "http://host.docker.internal:7897",
                    "ALL_PROXY": "socks5://host.docker.internal:7897"
                }
            }
            volumes = {}
            if self.workspace_dir is not None:
                os.makedirs(self.workspace_dir, exist_ok=True)
                volumes[os.path.abspath(self.workspace_dir)] = {"bind": self.container_workspace, "mode": "rw"}

            skill_host_dir = os.path.abspath("./data/skill")
            os.makedirs(skill_host_dir, exist_ok=True)
            volumes[skill_host_dir] = {"bind": f"{self.container_workspace}/skill", "mode": "rw"}

            buffer_host_dir = os.path.abspath("./.buffer")
            os.makedirs(buffer_host_dir, exist_ok=True)
            volumes[buffer_host_dir] = {"bind": f"{self.container_workspace}/.buffer", "mode": "rw"}

            from src.utils.config import FILE_CONFIG_PATH
            with open(FILE_CONFIG_PATH, "r") as f:
                docker_mount = json.load(f)
                docker_mount = docker_mount.get("docker_mount", [])
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
def call_base_tool(tool_name: str, arguments: dict) -> str:
    """
    统一调度 base_tool 模块下的工具
    【已脱壳】不做任何异常拦截，直接抛给上层 parse_tool
    返回: 格式化后的 JSON 字符串
    """
    result_content = ""

    if tool_name == "get_menu":
        result_content = get_menu(arguments.get("route"), arguments.get("plugin"))
    elif tool_name == "search_tool":
        result_content = search_tool(arguments.get("query"), arguments.get("top_k", 3))
    elif tool_name == "execute_command":
        result_content = execute_command(**arguments)
    elif tool_name == "fetch_tool":
        result_content = handle_fetch_tool(arguments)
    elif tool_name == "load_skill":
        result_content = load_skill(arguments.get("name"))
    elif tool_name == "list_skill":
        result_content = list_skill(arguments.get("page", 1))
    elif tool_name == "close_shell":
        result_content = close_shell(arguments.get("session_id", "default"))
    elif tool_name == "call_dynamic_tool":
        result_content = _format_response("error", "❌ 系统错误：代理工具拆包失败。请检查你传给 call_dynamic_tool 的 arguments 是否为合法的 JSON 字符串。")
    else:
        raise ValueError(f"未知的基础工具: {tool_name}")

    return result_content