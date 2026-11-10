"""工具管理 API：MCP / Skill / 闹钟 / 心跳与官方市场安装。

本模块只做路由声明与薄委托；注册表数据、校验、序列化与安装编排分别位于
tools_registry / tools_validation / tools_serialization / tools_market。
"""

from __future__ import annotations

import os
import shutil
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 引入底层工具操作
from src.tool.callmcp.schema_manager import load_cached_schemas, refresh_schemas
from src.tool.search.mcp_search import MCPSearcher, rebuild_vectors_async
from src.tool.search.skill_search import SkillSearcher, rebuild_skill_vectors_async
from src.tool.cron.cron_operations import list_crons, add_cron, delete_cron

from src.utils._fs import write_json_atomic
from src.utils.config import (
    AGENT_CORE_DIR,
    GRAPHS_DIR,
    GOAL_MD_PATH,
    HEARTBEAT_FILE,
    PARADIGMS_DIR,
    SENSOR_CONFIG_PATH,
    SENSOR_EXTENSION_DIR,
    get_mcp_config,
    get_sensor_config,
    _save_json_file,
)
from src.utils.graph_api import list_graphs
from src.utils.skill_helper import _find_skill_md_file

from src.server.api import common, plugin_runtime
from src.server.api.tools_market import (
    download_official_mcp_source as _download_official_mcp_source,
    download_skill_from_github as _download_skill_from_github,
    ensure_graph_mcp_deps as _ensure_graph_mcp_deps,
    ensure_graph_skill_deps as _ensure_graph_skill_deps,
    fetch_repo_zip as _fetch_repo_zip,
    http_download as _http_download,
    http_get_json as _http_get_json,
    install_agentloop_by_name as _install_agentloop_by_name,
    install_graph as _install_graph,
    install_graph_by_name as _install_graph_by_name,
    install_mcp_config as _install_mcp_config,
    install_sensor as _install_sensor,
    install_sensor_by_name as _install_sensor_by_name,
    install_skills_batch as _install_skills_batch,
    install_ui_plugin_by_name as _install_ui_plugin_by_name,
    uninstall_mcp as _uninstall_mcp,
)
from src.server.api.tools_registry import (
    AGENTLOOP_REGISTRY_URL,
    GRAPHS_REGISTRY_URL,
    MCP_REGISTRY_URL,
    SENSORS_REGISTRY_URL,
    SKILL_REGISTRY_URL,
    UI_PLUGIN_REGISTRY_URL,
    installed_graph_names,
    installed_sensor_entries,
    scan_installed_agentloops as _scan_installed_agentloops,
    scan_installed_ui_plugins as _scan_installed_ui_plugins,
)
from src.server.api.tools_serialization import (
    agentloop_registry_payload,
    graph_registry_payload,
    group_mcp_tools,
    heartbeat_payload,
    mcp_install_response,
    sensor_registry_payload,
    skill_batch_response,
    skill_install_response,
    ui_plugin_registry_payload,
)
from src.server.api.tools_validation import (
    parse_skill_github_url as _parse_skill_github_url,
    require_non_empty,
    require_plain_name,
    safe_install_name,
)
from src.server.api.webmin import SANDBOX_PLUGIN_ROOT, USER_PLUGIN_ROOT

router = APIRouter(prefix="/api/tools", tags=["Tools Management"])

# src/tool/kernelupgrade 以本模块作为市场实现入口懒加载这些名字，保留兼容。
__all__ = [
    "router",
    "_download_skill_from_github",
    "_download_official_mcp_source",
    "_ensure_graph_mcp_deps",
    "_ensure_graph_skill_deps",
    "_fetch_repo_zip",
    "_http_download",
    "_http_get_json",
    "_install_agentloop_by_name",
    "_install_graph_by_name",
    "_install_sensor_by_name",
    "_install_ui_plugin_by_name",
    "_parse_skill_github_url",
    "AGENTLOOP_REGISTRY_URL",
    "GRAPHS_REGISTRY_URL",
    "MCP_REGISTRY_URL",
    "SENSORS_REGISTRY_URL",
    "SKILL_REGISTRY_URL",
    "UI_PLUGIN_REGISTRY_URL",
]


# ==========================================
# 1. MCP 服务器名称和工具名称 API
# ==========================================
@router.get("/mcp")
def get_mcp_tools_api():
    """获取内存/缓存里的 MCP 服务器及其包含的工具名称和描述"""
    try:
        return group_mcp_tools(load_cached_schemas())
    except Exception as e:
        raise common.unexpected_error("获取 MCP 列表失败: ", e)


# ==========================================
# 2. Skill 名称和技能描述 API
# ==========================================
@router.get("/skills")
def get_skills_api():
    """获取内存里的 Skill 名称和描述"""
    try:
        searcher = SkillSearcher()
        # searcher.skills 是一个列表，格式如 [{"name": "...", "description": "...", "dir_name": "..."}]
        return searcher.skills
    except Exception as e:
        raise common.unexpected_error("获取 Skill 列表失败: ", e)


# ==========================================
# Skill 在线安装 API
# ==========================================
class InstallSkillReq(BaseModel):
    url: str


class InstallSkillsBatchReq(BaseModel):
    urls: list


@router.post("/skills/install")
def install_skill_api(req: InstallSkillReq):
    """根据 GitHub URL 下载第三方 Skill 并热更新内存"""
    try:
        skill_name = _download_skill_from_github(req.url)

        # 解压成功后，触发 searcher 的内存热更新
        SkillSearcher().reload_index()
        return skill_install_response(skill_name)

    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("Skill 下载/解压失败: ", e)


class UninstallSkillReq(BaseModel):
    name: str


@router.post("/skills/uninstall")
def uninstall_skill_api(req: UninstallSkillReq):
    """删除本地已安装的 Skill（目录名或 SKILL.md 的 name 匹配），并热更新内存"""
    try:
        name = require_non_empty(req.name, "缺少 skill name")

        md_file, _ = _find_skill_md_file(name)
        if not md_file.exists():
            raise HTTPException(
                status_code=404, detail=f"未找到已安装的 Skill '{name}'"
            )

        shutil.rmtree(md_file.parent)
        SkillSearcher().reload_index()
        return {"status": "success", "message": f"Skill '{name}' 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("删除 Skill 失败: ", e)


@router.post("/skills/install-batch")
def install_skills_batch_api(req: InstallSkillsBatchReq):
    """批量下载多个第三方 Skill 并热更新内存（同一仓库 zip 只下载一次）"""
    installed, failed = _install_skills_batch(req.urls)
    return skill_batch_response(installed, failed)


# ==========================================
# 3. Cron 闹钟列表 API
# ==========================================
@router.get("/cron")
def get_crons_api():
    """读取 cron.json 返回现有闹钟列表"""
    try:
        return list_crons()
    except Exception as e:
        raise common.unexpected_error("获取闹钟列表失败: ", e)


# ==========================================
# 4. MCP Schema 刷新 API
# ==========================================
# single-flight 门闸：刷新进行中时直接返回，防止连点导致全量刷新排队堆积
_MCP_REFRESH_GATE = threading.Lock()


@router.post("/mcp/refresh")
def refresh_mcp_api():
    """手动刷新 MCP Schema 并更新内存检索树"""
    if not _MCP_REFRESH_GATE.acquire(blocking=False):
        return {"status": "refreshing", "message": "MCP 正在刷新中，请稍候…"}
    try:
        # 1. 重新拉取物理文件
        schemas = refresh_schemas()
        # 2. 触发 Searcher 的内存热更新
        MCPSearcher().reload_index()
        # 3. 后台重建向量矩阵，避免刷新后首次搜索 JIT 卡顿
        rebuild_vectors_async()

        return {
            "status": "success",
            "message": f"MCP 缓存已刷新，共加载 {len(schemas)} 个工具",
        }
    except Exception as e:
        raise common.unexpected_error("刷新 MCP 失败: ", e)
    finally:
        _MCP_REFRESH_GATE.release()


# ==========================================
# MCP 录入安装 API
# ==========================================
class InstallMCPReq(BaseModel):
    config_json: str
    repo: str = ""  # 源码仓库地址；官方仓库（PurrPod/mcps）时额外下载源码


@router.post("/mcp/install")
def install_mcp_api(req: InstallMCPReq):
    """解析并合并用户传入的 MCP Server JSON 配置，落盘并热更新；官方 MCP 额外下载源码"""
    try:
        tool_count, source_note = _install_mcp_config(req.config_json, req.repo)
        return mcp_install_response(tool_count, source_note)
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("安装 MCP 失败: ", e)


class UninstallMCPReq(BaseModel):
    name: str


@router.post("/mcp/uninstall")
def uninstall_mcp_api(req: UninstallMCPReq):
    """从 mcp_config.json 移除该 Server，清理本地源码并热更新 Schema"""
    try:
        name = require_non_empty(req.name, "缺少 server 名")
        _uninstall_mcp(name)
        return {
            "status": "success",
            "message": f"MCP Server '{name}' 已删除",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("删除 MCP 失败: ", e)


# ==========================================
# MCP 已配置列表 API（市场"已安装"检测用）
# ==========================================
@router.get("/mcp/list")
def list_configured_mcps_api():
    """返回 mcp_config.json 中已配置的 MCP Server 名称列表"""
    try:
        config = get_mcp_config()
        return list(config.get("mcpServers", {}).keys())
    except Exception as e:
        raise common.unexpected_error("获取 MCP 配置列表失败: ", e)


# ==========================================
# 5. Skill 刷新 API
# ==========================================
_SKILL_REFRESH_GATE = threading.Lock()


@router.post("/skills/refresh")
def refresh_skills_api():
    """手动扫描本地 Skill 文件夹并更新内存检索树"""
    if not _SKILL_REFRESH_GATE.acquire(blocking=False):
        return {"status": "refreshing", "message": "Skill 正在刷新中，请稍候…"}
    try:
        searcher = SkillSearcher()
        searcher.reload_index()
        # 后台重建向量矩阵，避免刷新后首次搜索 JIT 卡顿
        rebuild_skill_vectors_async()

        return {
            "status": "success",
            "message": f"Skill 已刷新，共加载 {len(searcher.skills)} 个技能",
        }
    except Exception as e:
        raise common.unexpected_error("刷新 Skill 失败: ", e)
    finally:
        _SKILL_REFRESH_GATE.release()


# ==========================================
# 6. 添加、删除闹钟 API
# ==========================================
class AddCronReq(BaseModel):
    title: str
    trigger_time: str
    repeat_rule: str = "none"
    task_hook: str = "Agent"
    task_inputs: dict = {}


@router.post("/cron")
def add_cron_api(req: AddCronReq):
    """添加闹钟"""
    try:
        result = add_cron(
            title=req.title,
            trigger_time=req.trigger_time,
            repeat_rule=req.repeat_rule,
            task_hook=req.task_hook,
            task_inputs=req.task_inputs,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        raise common.unexpected_error("添加闹钟失败: ", e, status_code=400)


@router.delete("/cron/{identifier}")
def delete_cron_api(identifier: str):
    """删除闹钟 (支持传 id 或 title)"""
    try:
        result = delete_cron(identifier)
        return {"status": "success", "data": result}
    except Exception as e:
        raise common.unexpected_error("删除闹钟失败: ", e, status_code=400)


# ==========================================
# 7. Agent 心跳 API（GOAL.md 定时注入）
# ==========================================
class HeartbeatReq(BaseModel):
    interval: int  # 秒，最短 60
    active: bool
    goal: str = ""  # GOAL.md 内容；开启心跳时必填非空


@router.get("/heartbeat")
def get_heartbeat_api():
    """获取心跳配置 + GOAL.md 当前内容"""
    from src.agent.heartbeat import get_heartbeat_manager

    cfg = get_heartbeat_manager().get_config()
    return {
        "interval": cfg["interval"],
        "active": cfg["active"],
        "goal": get_heartbeat_manager().read_goal(),
    }


@router.post("/heartbeat")
def save_heartbeat_api(req: HeartbeatReq):
    """保存心跳配置；开启心跳时必须提交非空 GOAL.md 内容"""
    from src.agent.heartbeat import MIN_INTERVAL

    goal = (req.goal or "").strip()
    if req.active and not goal:
        raise HTTPException(status_code=400, detail="GOAL.md 内容为空，无法开启心跳")

    try:
        os.makedirs(AGENT_CORE_DIR, exist_ok=True)

        # 先落盘 GOAL.md
        with open(GOAL_MD_PATH, "w", encoding="utf-8") as f:
            f.write(req.goal or "")

        # 再落盘心跳配置（原子写入）
        cfg = heartbeat_payload(req.interval, req.active, MIN_INTERVAL)
        write_json_atomic(HEARTBEAT_FILE, cfg)
        return {"status": "success", "data": cfg}
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("保存心跳配置失败: ", e, status_code=400)


# ==========================================
# 8. Sensor 市场：Registry + 已安装列表 + 安装
# ==========================================
@router.get("/market/sensors")
def get_sensor_registry_api():
    """从官方 PurrPod/sensors 仓库拉取 registry.json 返回给前端市场"""
    try:
        return sensor_registry_payload(_http_get_json(SENSORS_REGISTRY_URL))
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("拉取 Sensor 注册表失败: ", e, status_code=502)


@router.get("/market/sensors/installed")
def list_installed_sensors_api():
    """返回 activate_sensor.json 中已配置（不管 enabled）的传感器名列表"""
    try:
        return installed_sensor_entries(get_sensor_config() or {}, SENSOR_EXTENSION_DIR)
    except Exception as e:
        raise common.unexpected_error("读取本地 Sensor 列表失败: ", e)


class InstallSensorReq(BaseModel):
    sensor: dict  # registry 中的单条 sensor 对象（含 name / description / enabled / env 等）


@router.post("/market/sensors/install")
def install_sensor_api(req: InstallSensorReq):
    """安装 Sensor：合并配置落盘并下载代码（支持覆盖式重新下载）。"""
    try:
        return _install_sensor(req.sensor or {})
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("安装 Sensor 失败: ", e)


class UninstallSensorReq(BaseModel):
    name: str


@router.post("/market/sensors/uninstall")
def uninstall_sensor_api(req: UninstallSensorReq):
    """从 activate_sensor.json 移除该 Sensor 并删除本地代码文件"""
    try:
        name = require_non_empty(req.name, "缺少 sensor 名")

        cfg = get_sensor_config() or {}
        if name not in cfg:
            raise HTTPException(status_code=404, detail=f"未配置 Sensor '{name}'")

        del cfg[name]
        os.makedirs(os.path.dirname(SENSOR_CONFIG_PATH), exist_ok=True)
        _save_json_file(SENSOR_CONFIG_PATH, cfg)

        code_file = os.path.join(SENSOR_EXTENSION_DIR, f"{name}.py")
        if os.path.exists(code_file):
            os.remove(code_file)

        return {"status": "success", "message": f"Sensor '{name}' 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("删除 Sensor 失败: ", e)


# ==========================================
# 9. Graph 市场：Registry + 已安装列表 + 安装
# ==========================================
@router.get("/market/graphs")
def get_graph_registry_api():
    """从官方 PurrPod/graphs 仓库拉取 registry.json 返回前端市场"""
    try:
        return graph_registry_payload(_http_get_json(GRAPHS_REGISTRY_URL))
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("拉取 Graph 注册表失败: ", e, status_code=502)


@router.get("/market/graphs/installed")
def list_installed_graphs_api():
    """返回 ~/.purrcat/graph 目录下已安装的 graph（文件夹结构）名字列表"""
    try:
        return installed_graph_names(list_graphs())
    except Exception as e:
        raise common.unexpected_error("读取本地 Graph 列表失败: ", e)


class InstallGraphReq(BaseModel):
    name: str


@router.post("/market/graphs/install")
def install_graph_api(req: InstallGraphReq):
    """安装 Graph（文件夹结构）并补齐其声明的 mcp/skill 依赖。"""
    try:
        return _install_graph(req.name)
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("安装 Graph 失败: ", e)


class UninstallGraphReq(BaseModel):
    name: str


@router.post("/market/graphs/uninstall")
def uninstall_graph_api(req: UninstallGraphReq):
    """删除 {GRAPHS_DIR}/{name} 文件夹（新目录结构）"""
    try:
        safe_name = safe_install_name(req.name, "缺少 graph name", "非法 graph name")

        target_dir = os.path.join(GRAPHS_DIR, safe_name)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail=f"未安装 Graph '{safe_name}'")

        shutil.rmtree(target_dir)
        return {"status": "success", "message": f"Graph '{safe_name}' 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("删除 Graph 失败: ", e)


# ==========================================
# 10. UI 插件市场：Registry + 已安装列表 + 安装（含依赖自动补齐）+ 卸载
# ==========================================
class InstallUiPluginReq(BaseModel):
    name: str


class UninstallUiPluginReq(BaseModel):
    name: str


@router.get("/market/ui-plugins")
def get_ui_plugin_registry_api():
    """从官方 PurrPod/ui-plugins 仓库拉取 registry.json 返回前端市场"""
    try:
        return ui_plugin_registry_payload(_http_get_json(UI_PLUGIN_REGISTRY_URL))
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("拉取 UI 插件注册表失败: ", e, status_code=502)


@router.get("/market/ui-plugins/installed")
def list_installed_ui_plugins_api():
    """返回已安装的 UI 插件名字列表（用户根 + 沙盒根两个可写根合并去重）"""
    try:
        return _scan_installed_ui_plugins()
    except Exception as e:
        raise common.unexpected_error("读取本地 UI 插件列表失败: ", e)


@router.post("/market/ui-plugins/install")
def install_ui_plugin_api(req: InstallUiPluginReq):
    """安装 UI 插件到其注册表条目声明的 root，并递归补齐依赖。"""
    try:
        name = require_non_empty(req.name, "缺少 UI 插件 name")
        notes = []
        res = _install_ui_plugin_by_name(name, notes, set())
        message = res.get("message") or f"UI 插件 '{name}' 已安装"
        if notes:
            message += "。" + "；".join(notes)
        return {"status": "success", "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("安装 UI 插件失败: ", e)


@router.post("/market/ui-plugins/uninstall")
def uninstall_ui_plugin_api(req: UninstallUiPluginReq):
    """卸载 UI 插件：在用户根 / 沙盒根中找到该插件目录，移动为同根下的 <name>.trash（可恢复）。"""
    try:
        name = require_plain_name(req.name, "非法的插件 name")

        target = None
        for root_dir in (USER_PLUGIN_ROOT, SANDBOX_PLUGIN_ROOT):
            cand = os.path.join(root_dir, name)
            if os.path.isdir(cand):
                target = cand
                break
        if target is None:
            raise HTTPException(status_code=404, detail=f"未安装 UI 插件 '{name}'")

        trash = f"{target}.trash"
        if os.path.exists(trash):
            shutil.rmtree(trash, ignore_errors=True)
        plugin_runtime.stop(name)  # 先停插件自带的后端子进程，再移动目录
        shutil.move(target, trash)
        return {"status": "success", "message": f"UI 插件 '{name}' 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("卸载 UI 插件失败: ", e)


# ==========================================
# 11. AgentLoop 市场：Registry + 已安装列表 + 安装（含依赖补齐）+ 卸载
# ==========================================
class InstallAgentloopReq(BaseModel):
    name: str


class UninstallAgentloopReq(BaseModel):
    name: str


@router.get("/market/agentloops")
def get_agentloop_registry_api():
    """从官方 PurrPod/agentloops 仓库拉取 registry.json 返回前端市场"""
    try:
        return agentloop_registry_payload(_http_get_json(AGENTLOOP_REGISTRY_URL))
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("拉取 AgentLoop 注册表失败: ", e, status_code=502)


@router.get("/market/agentloops/installed")
def list_installed_agentloops_api():
    """返回 paradigms 目录（~/.purrcat/paradigms）下已安装的 AgentLoop 名字列表"""
    try:
        return _scan_installed_agentloops(PARADIGMS_DIR)
    except Exception as e:
        raise common.unexpected_error("读取本地 AgentLoop 列表失败: ", e)


@router.post("/market/agentloops/install")
def install_agentloop_api(req: InstallAgentloopReq):
    """安装 AgentLoop（范式 YAML）到 ~/.purrcat/paradigms 并校验 hooks。"""
    try:
        name = require_plain_name(req.name, "非法的 AgentLoop name")
        return {"status": "success", "message": _install_agentloop_by_name(name)}
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("安装 AgentLoop 失败: ", e)


@router.post("/market/agentloops/uninstall")
def uninstall_agentloop_api(req: UninstallAgentloopReq):
    """卸载 AgentLoop：删除 paradigms 目录下对应的 YAML（默认 PARADIGM 除外）。"""
    try:
        name = require_plain_name(req.name, "非法的 AgentLoop name")
        if name.lower() == "paradigm":
            raise HTTPException(
                status_code=400, detail="默认 AgentLoop（PARADIGM）不可删除"
            )

        target = os.path.join(PARADIGMS_DIR, f"{name}.yaml")
        if not os.path.isfile(target):
            raise HTTPException(status_code=404, detail=f"未安装 AgentLoop '{name}'")
        os.remove(target)
        return {"status": "success", "message": f"AgentLoop '{name}' 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise common.unexpected_error("卸载 AgentLoop 失败: ", e)
