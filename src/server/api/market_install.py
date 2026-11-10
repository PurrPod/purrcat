"""工具市场安装编排：配置合并、按名安装、依赖补齐与卸载。

判定逻辑在 market_state，下载/解压在 market_archive；本模块只负责按步骤
落盘与热更新，并保留原有的 HTTPException 语义。
"""

from __future__ import annotations

import json
import os
import shutil

import yaml
from fastapi import HTTPException

from src.tool.callmcp.schema_manager import refresh_schemas
from src.tool.search.mcp_search import MCPSearcher, rebuild_vectors_async
from src.tool.search.skill_search import SkillSearcher, rebuild_skill_vectors_async
from src.server.api import plugin_runtime
from src.server.api.market_archive import (
    download_official_mcp_source,
    download_skill_from_github,
    extract_skill_from_zip,
    fetch_repo_zip,
    http_download,
    http_get_json,
)
from src.server.api.market_state import (
    drop_mcp_server,
    mcp_registry_entries,
    missing_names,
    required_files,
    resolve_mcp_dependencies,
    resolve_skill_install_plan,
    skill_registry_items,
)
from src.server.api.tools_registry import (
    AGENTLOOP_CODE_BASE,
    AGENTLOOP_REGISTRY_URL,
    GRAPHS_CODE_BASE,
    GRAPHS_REGISTRY_URL,
    MCP_REGISTRY_URL,
    SENSORS_CODE_BASE,
    SENSORS_REGISTRY_URL,
    SKILL_REGISTRY_URL,
    UI_PLUGIN_CODE_BASE,
    UI_PLUGIN_REGISTRY_URL,
    extract_registry_graphs,
    extract_registry_items,
    normalize_dependency_list,
)
from src.server.api.tools_serialization import merge_sensor_entry
from src.server.api.tools_validation import (
    parse_mcp_config_json,
    parse_skill_github_url,
    safe_install_name,
    safe_path_component,
    ui_plugin_root_dir,
    validate_registry_files,
)
from src.server.api.webmin import ROOT_TO_DIR, SANDBOX_PLUGIN_ROOT, USER_PLUGIN_ROOT
from src.utils.config import (
    GRAPHS_DIR,
    MCP_CONFIG_PATH,
    MCP_SOURCE_DIR,
    PARADIGMS_DIR,
    SENSOR_CONFIG_PATH,
    SENSOR_EXTENSION_DIR,
    _save_json_file,
    get_mcp_config,
    get_sensor_config,
)


def _download_to(url: str, dest: str) -> bytes:
    """下载单个文件到 dest，返回原始字节（目录不存在时自动创建）。"""
    raw = http_download(url)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(raw)
    return raw


def install_skills_batch(urls) -> tuple[list, list]:
    """批量安装 Skill：同一仓库 zip 只下载一次，返回 (installed, failed)。"""
    groups = {}
    for url in urls:
        owner, repo, branch, path = parse_skill_github_url(url)
        groups.setdefault((owner, repo, branch), []).append(path)

    installed, failed = [], []
    for (owner, repo, branch), paths in groups.items():
        try:
            zip_data = fetch_repo_zip(owner, repo, branch)
        except Exception as e:
            for path in paths:
                failed.append({"path": path or repo, "error": f"仓库下载失败: {e}"})
            continue

        for path in paths:
            try:
                installed.append(extract_skill_from_zip(zip_data, repo, path))
            except HTTPException as e:
                failed.append({"path": path or repo, "error": str(e.detail)})
            except Exception as e:
                failed.append({"path": path or repo, "error": str(e)})

    if installed:
        SkillSearcher().reload_index()
    return installed, failed


def install_mcp_config(config_json: str, repo: str = "") -> tuple[int, str]:
    """解析并合并用户粘贴的 MCP 配置，落盘后热更新，返回 (工具数, 源码说明)。"""
    new_config = parse_mcp_config_json(config_json)

    # 1. 读出现有配置
    existing_config = get_mcp_config()
    if "mcpServers" not in existing_config:
        existing_config["mcpServers"] = {}

    # 2. 遍历并合并配置
    for srv_name, srv_conf in new_config["mcpServers"].items():
        existing_config["mcpServers"][srv_name] = srv_conf

    # 3. 落盘保存配置文件 mcp_config.json
    os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_config, f, indent=2, ensure_ascii=False)

    # 4. 官方 MCP：下载源码到 ~/.purrcat/mcps/（失败不阻断配置安装）
    source_note = ""
    try:
        downloaded = download_official_mcp_source(
            repo, list(new_config["mcpServers"].keys())
        )
        if downloaded:
            source_note = f"；已下载官方源码: {downloaded}"
    except Exception as e:
        import traceback

        traceback.print_exc()
        source_note = f"；官方源码下载失败: {e}"

    # 5. 刷新 Schema 并重建检索树（会自动通信子进程并更新 mcp_schema.json）
    schemas = refresh_schemas()
    MCPSearcher().reload_index()
    rebuild_vectors_async()
    return len(schemas), source_note


def uninstall_mcp(name: str) -> None:
    """从 mcp_config.json 移除 Server，清理官方源码目录并热更新 Schema。"""
    existing = get_mcp_config()
    drop_mcp_server(existing, name)
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    # 清理官方源码目录（若有）
    src_dir = os.path.join(MCP_SOURCE_DIR, name)
    if os.path.isdir(src_dir):
        shutil.rmtree(src_dir)

    refresh_schemas()
    MCPSearcher().reload_index()
    rebuild_vectors_async()


def ensure_graph_mcp_deps(mcp_names) -> list:
    """本地缺失的 MCP 依赖从市场安装；市场也缺失时跳过。返回处理说明列表。"""
    names = [str(n).strip() for n in (mcp_names or []) if str(n).strip()]
    if not names:
        return []

    configured = set(get_mcp_config().get("mcpServers", {}).keys())
    missing = missing_names(names, configured)
    if not missing:
        return []

    entries = mcp_registry_entries(http_get_json(MCP_REGISTRY_URL))
    merged_servers, repo_server_pairs, notes = resolve_mcp_dependencies(
        entries, missing
    )
    if not merged_servers:
        return notes

    # 合并配置落盘
    existing_config = get_mcp_config()
    existing_config.setdefault("mcpServers", {}).update(merged_servers)
    os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_config, f, indent=2, ensure_ascii=False)

    # 官方源码下载（失败不阻断配置安装）
    for repo, server_names in repo_server_pairs:
        try:
            download_official_mcp_source(repo, server_names)
        except Exception:
            import traceback

            traceback.print_exc()

    # 热更新 Schema 与检索树
    refresh_schemas()
    MCPSearcher().reload_index()
    rebuild_vectors_async()
    notes.append(f"已从市场自动安装 MCP 依赖: {', '.join(merged_servers.keys())}")
    return notes


def ensure_graph_skill_deps(skill_names) -> list:
    """本地缺失的 Skill 依赖从市场安装；市场也缺失时跳过。返回处理说明列表。"""
    names = [str(n).strip() for n in (skill_names or []) if str(n).strip()]
    if not names:
        return []

    try:
        local_names = []
        for s in SkillSearcher().skills:
            local_names.append(str(s.get("name", "")))
            local_names.append(str(s.get("dir_name", "")))
    except Exception:
        local_names = []

    missing = missing_names(names, local_names, ignore_case=True)
    if not missing:
        return []

    items = skill_registry_items(http_get_json(SKILL_REGISTRY_URL))
    plan, notes = resolve_skill_install_plan(items, missing)

    installed = []
    for name, link in plan:
        try:
            installed.append(download_skill_from_github(link))
        except Exception as e:
            import traceback

            traceback.print_exc()
            notes.append(f"Skill '{name}' 安装失败({e})，已跳过")

    if installed:
        SkillSearcher().reload_index()
        rebuild_skill_vectors_async()
        notes.append(f"已从市场自动安装 Skill 依赖: {', '.join(installed)}")
    return notes


def install_sensor(sensor: dict) -> dict:
    """安装 Sensor：先合并配置落盘，再下载代码（下载失败返回 partial）。"""
    sensor = sensor or {}
    name = str(sensor.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="sensor 缺少 name 字段")

    # 1. 合并配置：已有配置的 env 非空值不被 registry 占位覆盖
    existing_cfg = get_sensor_config() or {}
    existing_entry = (
        existing_cfg.get(name, {}) if isinstance(existing_cfg, dict) else {}
    )
    existing_cfg[name] = merge_sensor_entry(sensor, existing_entry)
    os.makedirs(os.path.dirname(SENSOR_CONFIG_PATH), exist_ok=True)
    _save_json_file(SENSOR_CONFIG_PATH, existing_cfg)

    # 2. 下载代码：优先 sensors/<name>/<name>.py，其次 sensors/<name>.py
    code_bytes = None
    last_err = None
    for candidate in (
        f"{SENSORS_CODE_BASE}/{name}/{name}.py",
        f"{SENSORS_CODE_BASE}/{name}.py",
    ):
        try:
            code_bytes = http_download(candidate)
            break
        except Exception as e:  # noqa: PERF203
            last_err = e
            code_bytes = None
    if code_bytes is None:
        # 代码下载失败不阻断配置落盘（SensorManager 启动时会再次尝试从官方 sensors 仓库下载）
        msg = (
            f"Sensor '{name}' 配置已写入激活配置，但代码文件下载失败"
            + (f": {last_err}" if last_err else "")
            + "；启动阶段会再次尝试从官方 sensors 仓库下载。"
        )
        return {"status": "partial", "message": msg, "code_downloaded": False}

    os.makedirs(SENSOR_EXTENSION_DIR, exist_ok=True)
    dest = os.path.join(SENSOR_EXTENSION_DIR, f"{name}.py")
    with open(dest, "wb") as f:
        f.write(code_bytes)
    return {
        "status": "success",
        "message": f"Sensor '{name}' 配置已合并，代码已下载到 {dest}。",
        "code_downloaded": True,
    }


def install_sensor_by_name(name: str) -> str:
    """按名字从官方 sensors 市场安装一个 Sensor，返回处理说明。"""
    safe_name = safe_path_component(name, "非法 sensor name")
    registry = http_get_json(SENSORS_REGISTRY_URL)
    sensors = registry.get("sensors", []) if isinstance(registry, dict) else []
    entry = next(
        (
            s
            for s in sensors
            if isinstance(s, dict)
            and str(s.get("name", "")).strip().lower() == safe_name.lower()
        ),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"市场注册表中找不到 Sensor '{safe_name}'"
        )
    try:
        res = install_sensor(entry)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安装 Sensor 失败: {e}")
    return (res or {}).get("message") or f"Sensor '{safe_name}' 已安装"


def install_graph(name: str) -> dict:
    """从 registry 下载 Graph 文件夹到 GRAPHS_DIR，并补齐其 mcp/skill 依赖。"""
    safe_name = safe_install_name(name, "缺少 graph name", "非法 graph name")

    # 1) 从 registry 取条目与文件清单
    try:
        registry = http_get_json(GRAPHS_REGISTRY_URL)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"拉取 Graph 注册表失败: {e}")
    entry = next(
        (
            g
            for g in extract_registry_graphs(registry)
            if isinstance(g, dict)
            and str(g.get("name", "")).strip().lower() == safe_name.lower()
        ),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"市场注册表中找不到 Graph '{safe_name}'"
        )

    files = required_files(entry.get("files"), "graph.json")
    validate_registry_files(files)

    # 2) 重装场景下清掉旧目录，保证与市场版本一致
    target_dir = os.path.join(GRAPHS_DIR, safe_name)
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    graph_data = None
    downloaded = []
    for rel in files:
        url = f"{GRAPHS_CODE_BASE}/{safe_name}/{rel}"
        try:
            dest = os.path.join(target_dir, *rel.replace("\\", "/").split("/"))
            raw = _download_to(url, dest)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"下载 Graph 文件失败 ({url}): {e}"
            )
        downloaded.append(rel)

        if rel == "graph.json":
            try:
                graph_data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise HTTPException(status_code=502, detail=f"Graph JSON 解析失败: {e}")

    if not isinstance(graph_data, dict):
        raise HTTPException(status_code=502, detail="Graph JSON 顶层必须是对象")

    # 依赖补齐：graph 声明的 mcps/skills，本地缺失的先从市场安装（缺失即跳过）
    try:
        deps = graph_data.get("dependencies", {}) or {}
        dep_notes = ensure_graph_mcp_deps(deps.get("mcps", []))
        dep_notes += ensure_graph_skill_deps(deps.get("skills", []))
    except Exception as e:
        import traceback

        traceback.print_exc()
        dep_notes = [f"依赖检测失败({e})，已跳过"]

    message = f"Graph '{safe_name}' 已安装到 {target_dir}（{len(downloaded)} 个文件）"
    if dep_notes:
        message += "。" + "；".join(dep_notes)
    return {"status": "success", "message": message}


def install_graph_by_name(name: str) -> dict:
    """按名字从官方 graphs 市场安装一个 Graph（含其声明的 mcp/skill 依赖）。"""
    try:
        return install_graph(name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安装 Graph 失败: {e}")


def install_agentloop_by_name(name: str) -> str:
    """按名字从官方 agentloop 市场安装一个 Agent Loop（范式）到 paradigms 目录。"""
    safe_name = safe_path_component(name, "非法 agentloop name")

    registry = http_get_json(AGENTLOOP_REGISTRY_URL)
    entry = next(
        (
            a
            for a in extract_registry_items(registry, "agentloops")
            if isinstance(a, dict)
            and str(a.get("name", "")).strip().lower() == safe_name.lower()
        ),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"市场注册表中找不到 AgentLoop '{safe_name}'"
        )

    files = required_files(entry.get("files"), f"{safe_name}.yaml")
    validate_registry_files(files)

    os.makedirs(PARADIGMS_DIR, exist_ok=True)
    written = []
    for rel in files:
        url = f"{AGENTLOOP_CODE_BASE}/{rel}"
        try:
            dest = os.path.join(PARADIGMS_DIR, *rel.replace("\\", "/").split("/"))
            _download_to(url, dest)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"下载 AgentLoop 文件失败 ({url}): {e}"
            )
        written.append(rel)

    # 落盘后做一次 YAML 解析校验：失败时报错但不回滚已写入文件
    for rel in written:
        if not rel.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(PARADIGMS_DIR, *rel.replace("\\", "/").split("/"))
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict) or not data.get("hooks"):
                raise ValueError("YAML 缺少 hooks 字段")
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"AgentLoop 文件校验失败 ({rel}): {e}"
            )

    return f"AgentLoop '{safe_name}' 已安装到 {PARADIGMS_DIR}（{len(written)} 个文件）"


def install_ui_plugin_entry(entry: dict, notes: list, seen: set) -> dict:
    """按注册表条目把 UI 插件文件夹落盘到其声明的 root，然后递归补齐其依赖。"""
    name = str(entry.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=502, detail="UI 插件注册表条目缺少 name")

    files = required_files(entry.get("files"), "plugin.json")
    validate_registry_files(files)

    # 落盘根由注册表条目声明的 root 决定（user → 用户根，sandbox → 沙盒根），
    # 不再全部塞进用户根；内置插件不接受市场安装。
    root_dir = ui_plugin_root_dir(entry.get("root"), ROOT_TO_DIR, USER_PLUGIN_ROOT)
    # 重装场景：清掉两个可写根下同名的旧目录，避免旧根残留把新装位置遮住（用户根优先级更高）
    for stale_root in (USER_PLUGIN_ROOT, SANDBOX_PLUGIN_ROOT):
        stale_dir = os.path.join(stale_root, name)
        if os.path.isdir(stale_dir):
            plugin_runtime.stop(name)
            shutil.rmtree(stale_dir)
    target_dir = os.path.join(root_dir, name)
    os.makedirs(target_dir, exist_ok=True)

    plugin_data = None
    downloaded = []
    for rel in files:
        url = f"{UI_PLUGIN_CODE_BASE}/{name}/{rel}"
        try:
            dest = os.path.join(target_dir, *rel.replace("\\", "/").split("/"))
            raw = _download_to(url, dest)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"下载 UI 插件文件失败 ({url}): {e}"
            )
        downloaded.append(rel)
        if rel == "plugin.json":
            try:
                plugin_data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise HTTPException(
                    status_code=502, detail=f"UI 插件 plugin.json 解析失败: {e}"
                )

    if not isinstance(plugin_data, dict):
        raise HTTPException(status_code=502, detail="UI 插件缺少合法的 plugin.json")

    # 依赖：注册表条目声明优先，其次回退到 plugin.json 的 dependency 字段
    deps = normalize_dependency_list(entry.get("dependency"))
    if not deps:
        deps = normalize_dependency_list(plugin_data.get("dependency"))
    for dep in deps:
        ensure_market_dep(dep["type"], dep["id"], notes, seen)

    return {
        "status": "success",
        "message": f"UI 插件 '{name}' 已安装到 {target_dir}（{len(downloaded)} 个文件）",
    }


def install_ui_plugin_by_name(name: str, notes: list = None, seen: set = None) -> dict:
    """从官方 ui-plugin 仓库按名字安装一个 UI 插件（seen 防依赖成环）。"""
    notes = notes if notes is not None else []
    seen = seen if seen is not None else set()
    safe_name = safe_path_component(name, "非法 UI 插件 name")
    if safe_name in seen:
        return {
            "status": "skip",
            "message": f"UI 插件 '{safe_name}' 已在本次安装链中处理过",
        }
    seen.add(safe_name)

    registry = http_get_json(UI_PLUGIN_REGISTRY_URL)
    entry = next(
        (
            p
            for p in extract_registry_items(registry, "plugins")
            if isinstance(p, dict)
            and str(p.get("name", "")).strip().lower() == safe_name.lower()
        ),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"市场注册表中找不到 UI 插件 '{safe_name}'"
        )
    return install_ui_plugin_entry(entry, notes, seen)


def ensure_market_dep(dep_type: str, dep_id: str, notes: list, seen: set) -> None:
    """按类型把一个依赖交给对应安装通道；失败只记 notes，不中断整单安装。"""
    try:
        if dep_type == "skill":
            notes.extend(ensure_graph_skill_deps([dep_id]))
        elif dep_type == "mcp":
            notes.extend(ensure_graph_mcp_deps([dep_id]))
        elif dep_type == "sensor":
            notes.append(install_sensor_by_name(dep_id))
        elif dep_type == "graph":
            notes.append(
                install_graph_by_name(dep_id).get("message")
                or f"Graph '{dep_id}' 已安装"
            )
        elif dep_type == "plugin":
            notes.append(
                install_ui_plugin_by_name(dep_id, notes, seen).get("message")
                or f"UI 插件 '{dep_id}' 已处理"
            )
        elif dep_type == "agentloop":
            notes.append(install_agentloop_by_name(dep_id))
        else:
            notes.append(f"不支持的依赖类型 '{dep_type}'，已跳过")
    except HTTPException as e:
        notes.append(f"{dep_type} 依赖 '{dep_id}' 安装失败({e.detail})，已跳过")
    except Exception as e:
        import traceback

        traceback.print_exc()
        notes.append(f"{dep_type} 依赖 '{dep_id}' 安装失败({e})，已跳过")
