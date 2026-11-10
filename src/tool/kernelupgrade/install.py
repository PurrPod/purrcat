"""KernelUpgrade(action='install')：从官方市场 / URL 安装到正式区

复用插件市场已有实现（src/server/api/tools.py）：
- skill / sensor / graph / agentloop / ui-plugin：按官方收录名安装
- skill / graph / agentloop：也可传 GitHub URL 或 YAML 路径
- mcp：官方收录名（下载源码 + 合并配置），或直接传 mcpServers 配置串（仅合并配置）
"""

import io
import json
import os
import shutil
import zipfile

from src.tool.utils.format import error_response, text_response
from src.utils.config import SKILL_DIR
from .shared import is_url, market, normalize_target, resolve_agent_vm_path


def install_module(t: str, target: str) -> dict:
    m = market()
    # Agent 常把 URL/配置串包在反引号或引号里，先剥掉外层包装再判类型
    raw = normalize_target(target)
    if not raw:
        return error_response(
            "install 需要 target（名字 / URL / MCP 配置串）", "❌ 参数错误"
        )

    if t == "skill":
        return _install_skill(raw, m)
    if t == "mcp":
        return _install_mcp(raw, m)
    if t == "sensor":
        return _install_sensor(raw, m)
    if t == "graph":
        return _install_graph(raw, m)
    if t == "agentloop":
        return _install_agentloop(raw, m)
    return _install_ui_plugin(raw, m)


# ------------------------------------------
# skill
# ------------------------------------------
def _install_skill(target: str, m) -> dict:
    """target = 官方市场收录名；或 GitHub URL；或本地文件夹路径（需含 SKILL.md）"""
    if is_url(target):
        name = m._download_skill_from_github(target)
    else:
        local_dir = _local_skill_dir(target)
        if local_dir is not None:
            if not os.path.exists(os.path.join(local_dir, "SKILL.md")):
                return error_response(
                    f"❌ 目录 '{local_dir}' 下未找到 SKILL.md，无法作为 Skill 安装。",
                    "❌ 缺少 SKILL.md",
                )
            name = _copy_skill_dir(local_dir)
        else:
            registry = m._http_get_json(m.SKILL_REGISTRY_URL)
            raw = registry.get("skills", {}) if isinstance(registry, dict) else {}
            items = list(raw.items()) if isinstance(raw, dict) else enumerate(raw or [])
            link = ""
            for key, entry in items:
                if not isinstance(entry, dict):
                    continue
                if (
                    str(key or "").lower() == target.lower()
                    or str(entry.get("name", "")).lower() == target.lower()
                ):
                    link = entry.get("skill-single-link") or ""
                    break
            if not link:
                return error_response(
                    f"❌ '{target}' 不是可访问的本地目录，市场注册表中也找不到该 Skill。",
                    "❌ 未收录",
                )
            name = m._download_skill_from_github(link)

    _reload_skills()
    return text_response(
        f"✅ Skill '{name}' 已安装并热加载入内存！",
        f"🧩 Skill {name} 已安装",
    )


def _local_skill_dir(target: str) -> str | None:
    """target 指向存在的本地目录时返回其路径（兼容 /agent_vm/ 沙盒视角前缀），否则 None"""
    path = resolve_agent_vm_path(target)
    return path if os.path.isdir(path) else None


def _copy_skill_dir(src_dir: str) -> str:
    """把本地 Skill 文件夹覆盖式拷入正式区，返回 skill 名（取文件夹名）"""
    src = os.path.abspath(src_dir)
    name = os.path.basename(os.path.normpath(src))
    dest = os.path.join(SKILL_DIR, name)
    # 来源已在正式区时无需自拷贝（否则会先删后拷把源一起删掉）
    if os.path.abspath(dest) != src:
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(SKILL_DIR, exist_ok=True)
        shutil.copytree(src, dest)
    return name


def _reload_skills():
    from src.tool.search.skill_search import SkillSearcher, rebuild_skill_vectors_async

    SkillSearcher().reload_index()
    rebuild_skill_vectors_async()


# ------------------------------------------
# mcp
# ------------------------------------------
def _install_mcp(target: str, m) -> dict:
    """target = 官方收录名（下载源码 + 合并配置）；或 mcpServers 配置串（仅合并配置）"""
    if target.lstrip().startswith("{"):
        try:
            new_config = json.loads(target)
        except json.JSONDecodeError as e:
            return error_response(f"MCP 配置串不是合法 JSON：{e}", "❌ JSON 非法")
        if "mcpServers" not in new_config:
            return error_response(
                "MCP 配置串必须以 'mcpServers' 为顶层键", "❌ 配置格式错误"
            )
        _merge_mcp_servers(new_config["mcpServers"])
        note = _refresh_mcp(m)
        return text_response(
            f"✅ MCP 配置已合并落盘（{', '.join(new_config['mcpServers'].keys())}）"
            f"并热加载{note}",
            "🔌 MCP 配置已合并",
        )

    # 官方收录名：查 registry → 合并配置 + 下载官方源码
    registry = m._http_get_json(m.MCP_REGISTRY_URL)
    raw = registry.get("mcps", []) if isinstance(registry, dict) else registry
    entries = list(raw.values()) if isinstance(raw, dict) else (raw or [])
    entry = None
    for e in entries:
        if not isinstance(e, dict):
            continue
        servers = e.get("mcpServers") or {}
        if str(e.get("name", "")).lower() == target.lower() or any(
            k.lower() == target.lower() for k in servers
        ):
            entry = e
            break
    if not entry or not entry.get("mcpServers"):
        return error_response(
            f"❌ 市场注册表中找不到 MCP '{target}'。"
            "若是自建配置，请直接把 mcpServers 配置串作为 target 传入。",
            "❌ 未收录",
        )

    _merge_mcp_servers(entry["mcpServers"])
    source_note = ""
    try:
        downloaded = m._download_official_mcp_source(
            entry.get("repo") or "", list(entry["mcpServers"].keys())
        )
        if downloaded:
            source_note = f"，已下载官方源码: {downloaded}"
    except Exception as e:
        source_note = f"，官方源码下载失败: {e}"
    note = _refresh_mcp(m)
    return text_response(
        f"✅ MCP '{target}' 配置已合并并热加载{source_note}{note}",
        f"🔌 {target} MCP已安装",
    )


def _merge_mcp_servers(servers: dict):
    from src.utils.config import MCP_CONFIG_PATH, get_mcp_config

    config = get_mcp_config()
    config.setdefault("mcpServers", {}).update(servers)
    os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _refresh_mcp(m) -> str:
    try:
        schemas = m.refresh_schemas()
        m.MCPSearcher().reload_index()
        m.rebuild_vectors_async()
        return f"（当前系统共载入 {len(schemas)} 个 MCP 工具）"
    except Exception as e:
        return f"（热加载失败，可稍后手动刷新：{e}）"


# ------------------------------------------
# sensor
# ------------------------------------------
def _install_sensor(target: str, m) -> dict:
    msg = m._install_sensor_by_name(target)
    return text_response(f"✅ {msg}", f"📡 Sensor {target} 已安装")


# ------------------------------------------
# graph
# ------------------------------------------
def _install_graph(target: str, m) -> dict:
    if is_url(target):
        name = _install_graph_from_url(target, m)
        dep_note = _ensure_url_graph_deps(m, name)
        return text_response(
            f"✅ Graph '{name}' 已从 URL 安装到正式图形目录。{dep_note}",
            f"🕸️ Graph {name} 已安装",
        )

    # 官方收录名：走市场安装（自动补齐其声明的 mcp/skill 依赖）
    res = m._install_graph_by_name(target)
    msg = res.get("message") if isinstance(res, dict) else ""
    return text_response(
        f"✅ Graph '{target}' 已安装到正式图形目录。\n{msg or ''}",
        f"🕸️ Graph {target} 已安装",
    )


def _ensure_url_graph_deps(m, name: str) -> str:
    """URL 安装的 Graph：读取 graph.json 声明的 mcp/skill 依赖并尝试从市场补齐（缺失即跳过）"""
    from src.utils.config import GRAPHS_DIR

    graph_json = os.path.join(GRAPHS_DIR, name, "graph.json")
    try:
        with open(graph_json, "r", encoding="utf-8") as f:
            deps = json.load(f).get("dependencies") or {}
        notes = m._ensure_graph_mcp_deps(deps.get("mcps", []))
        notes += m._ensure_graph_skill_deps(deps.get("skills", []))
        return ("\n" + "；".join(notes)) if notes else ""
    except Exception:
        return ""


def _install_graph_from_url(url: str, m) -> str:
    """URL 指向 GitHub 仓库中含 graph.json 的文件夹，下载整个文件夹落正式图形目录"""
    from src.utils.config import GRAPHS_DIR

    owner, repo, branch, path = m._parse_skill_github_url(url)
    zip_data = m._fetch_repo_zip(owner, repo, branch)

    name = os.path.basename(path) if path else repo
    dest_dir = os.path.join(GRAPHS_DIR, name)

    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        root_folder = z.namelist()[0].split("/")[0]
        prefix = f"{root_folder}/{path}".rstrip("/") + "/"
        graph_json_in_zip = prefix + "graph.json"
        if not any(
            not f.is_dir()
            and f.filename.rstrip("/").lower() == graph_json_in_zip.lower()
            for f in z.infolist()
        ):
            raise ValueError(f"目录 '{path or repo}' 下未找到 graph.json")

        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        for fi in z.infolist():
            if not fi.filename.startswith(prefix):
                continue
            rel = fi.filename[len(prefix) :]
            if not rel:
                continue
            local = os.path.join(dest_dir, rel)
            if fi.is_dir():
                os.makedirs(local, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(local), exist_ok=True)
                with open(local, "wb") as f:
                    f.write(z.read(fi.filename))
    return name


# ------------------------------------------
# agentloop
# ------------------------------------------
def _install_agentloop(target: str, m) -> dict:
    """target = 官方收录名 / YAML 文件路径 / YAML URL"""
    from src.utils.config import PARADIGMS_DIR

    if target.startswith(("http://", "https://")):
        raw = m._http_download(target)
        name = (
            os.path.splitext(os.path.basename(target.split("?")[0]))[0] or "agentloop"
        )
        _write_agentloop_yaml(PARADIGMS_DIR, name, raw)
        return text_response(
            f"✅ AgentLoop '{name}' 已从 URL 安装到 {PARADIGMS_DIR}。",
            f"🔄 {name} AgentLoop已安装",
        )

    if target.lower().endswith((".yaml", ".yml")):
        path = resolve_agent_vm_path(target)
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, "rb") as f:
            raw = f.read()
        _write_agentloop_yaml(PARADIGMS_DIR, name, raw)
        return text_response(
            f"✅ AgentLoop '{name}' 已从文件安装到 {PARADIGMS_DIR}。",
            f"🔄 {name} AgentLoop已安装",
        )

    msg = m._install_agentloop_by_name(target)
    return text_response(f"✅ {msg}", f"🔄 {target} AgentLoop已安装")


def _write_agentloop_yaml(root: str, name: str, raw: bytes):
    import yaml

    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"AgentLoop YAML 解析失败: {e}")
    if not isinstance(data, dict) or not data.get("hooks"):
        raise ValueError("AgentLoop YAML 缺少 hooks 字段")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, f"{name}.yaml"), "wb") as f:
        f.write(raw)


# ------------------------------------------
# ui-plugin
# ------------------------------------------
def _install_ui_plugin(target: str, m) -> dict:
    res = m._install_ui_plugin_by_name(target, [], set())
    msg = res.get("message") if isinstance(res, dict) else None
    return text_response(
        f"✅ {msg or f'UI 插件 {target} 已安装'}",
        f"🧩 UI插件 {target} 已安装",
    )
