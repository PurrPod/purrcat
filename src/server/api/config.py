"""配置中心 API：路由声明与薄委托（SPEC-020）。

参数校验在 config_validation.py，Sensor/数据根/磁盘编排在 config_services.py；
本文件只保留路由表与需要就地读取的只读状态。
"""

import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Body

# 👇 引入全局的 agent_manager
from src.agent.manager import manager as agent_manager

from src.api_port import read_runtime_port

from src.server.api import common, config_services, config_validation
from src.utils.config import (
    FILE_CONFIG_PATH,
    MCP_CONFIG_PATH,
    MODEL_CONFIG_PATH,
    AGENT_CORE_DIR,
    GLOBAL_CONFIG_FILE,
    CRON_FILE,
    get_file_config,
    get_mcp_config,
    get_model_config,
    get_sensor_config,
    is_data_root_configured,
    save_global_setting,
    PURRCAT_DIR,
    DATA_ROOT,
    BASE_DIR,
)

router = APIRouter(prefix="/api/config", tags=["Configuration"])


def _save_json_file(file_path: str, data: Dict[str, Any]) -> bool:
    """通用的 JSON 写入方法"""
    return common.save_json_file(file_path, data, log_prefix="[Config API]")


# ── Model Config ──
@router.get("/model")
def api_get_model_config():
    return get_model_config()


@router.put("/model")
def api_update_model_config(config: Dict[str, Any]):
    if _save_json_file(MODEL_CONFIG_PATH, config):
        # 👇 保存 JSON 成功后，立刻通知内存中的 Agent 热重载！
        agent_manager.reload_model()
        return {
            "status": "ok",
            "message": "Model config updated and reloaded successfully",
        }
    raise HTTPException(status_code=500, detail="Failed to save model config")


# ── Sensor Config ──
@router.get("/sensor")
def api_get_sensor_config():
    return get_sensor_config()


@router.put("/sensor")
def api_update_sensor_config(config: Dict[str, Any]):
    return config_services.save_sensor_config(config)


@router.post("/sensor/reload")
def api_reload_sensor_manager():
    return config_services.reload_sensors()


@router.get("/sensor/runtime")
def api_get_sensor_runtime():
    return config_services.list_running_sensors()


@router.post("/sensor/{name}/stop")
def api_stop_sensor(name: str):
    return config_services.stop_sensor(name)


@router.post("/sensor/{name}/purge")
def api_purge_sensor(name: str):
    return config_services.purge_sensor(name)


@router.post("/sensor/{name}/restart")
def api_restart_sensor(name: str):
    return config_services.restart_sensor(name)


# ── File Config ──
@router.get("/file")
def api_get_file_config():
    return get_file_config()


@router.put("/file")
def api_update_file_config(config: Dict[str, Any]):
    if _save_json_file(FILE_CONFIG_PATH, config):
        return {"status": "ok", "message": "File config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save file config")


# ── MCP Config ──
@router.get("/mcp")
def api_get_mcp_config():
    return get_mcp_config()


@router.put("/mcp")
def api_update_mcp_config(config: Dict[str, Any]):
    if _save_json_file(MCP_CONFIG_PATH, config):
        return {"status": "ok", "message": "MCP config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save MCP config")


@router.post("/mcp/reload")
def api_reload_mcp_runtime():
    """重新握手所有 MCP Server（新增的即时拉起、改配置的自动重启子进程），
    重建 schema 缓存并热更新内存检索树"""
    try:
        from src.tool.callmcp.callmcp import reload_mcp_schema_core

        count = reload_mcp_schema_core()
        return {
            "status": "ok",
            "message": f"MCP 已重载到内存：检索树已热更新，共 {count} 个工具",
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"MCP 重载失败: {str(e)}")


# ── ACP 编辑器接入（任意 ACP 客户端：编辑器 / IDE 等）──


@router.get("/acp")
def api_get_acp_status():
    """ACP 接入状态：relay 部署情况 / 端口 / uv 可用性"""
    import shutil

    from src.utils.config import ACP_RELAY_PATH, get_global_settings

    source = os.path.join(BASE_DIR, "scripts", "acp_relay.py")
    source_found = os.path.isfile(source)
    deployed = os.path.isfile(ACP_RELAY_PATH)
    matches = False
    if deployed and source_found:
        try:
            with open(ACP_RELAY_PATH, "r", encoding="utf-8") as f:
                deployed_src = f.read()
            with open(source, "r", encoding="utf-8") as f:
                matches = deployed_src == f.read()
        except Exception:
            matches = False

    port = get_global_settings().get("acp_port")
    configured_port = port if isinstance(port, int) and 0 < port < 65536 else None
    # 🌟 本次运行真实 bind 的端口（后端写在 runtime.json）：端口 fallback 后它与
    # settings.acp_port（用户期望值）会不一致，面板按实际端口展示才不误导
    actual_port = read_runtime_port()
    return {
        "relay_path": ACP_RELAY_PATH,
        "relay_deployed": deployed,
        "relay_source_found": source_found,
        "relay_matches_source": matches,
        "port": configured_port or 8000,
        "actual_port": actual_port,
        "port_mismatch": bool(
            configured_port and actual_port and configured_port != actual_port
        ),
        "uv_found": shutil.which("uv") is not None,
    }


def _validate_acp_port(port) -> int:
    """兼容旧入口；校验实现见 config_validation。"""
    return config_validation.validate_acp_port(port)


@router.put("/acp")
def api_update_acp_config(payload: Dict[str, Any]):
    """更新 ACP 接入设置（目前仅后端端口，写入 settings.json 的 acp_port）"""
    port = payload.get("port")
    if port is not None:
        _validate_acp_port(port)
        if not save_global_setting("acp_port", port):
            raise HTTPException(status_code=500, detail="保存 acp_port 失败")
    return {"status": "ok", "message": "ACP settings updated"}


@router.post("/acp/redeploy")
def api_redeploy_acp_relay():
    """重新部署 relay 脚本（文件被误删 / 版本落后时的一键修复）"""
    from src.utils.initial import deploy_acp_relay

    if not deploy_acp_relay(force=True):
        raise HTTPException(status_code=500, detail="部署失败：内置源缺失或写入错误")
    return api_get_acp_status() | {"status": "ok"}


@router.post("/acp/reset-token")
def api_reset_acp_token():
    """重置 ACP 网关 token（旧令牌立即失效；客户端侧 relay 需重启后重连）"""
    from src.utils.config import ACP_TOKEN_FILE, get_acp_token

    try:
        if os.path.exists(ACP_TOKEN_FILE):
            os.remove(ACP_TOKEN_FILE)
        get_acp_token()  # 立即重新生成
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"token 重置失败: {e}")
    return {"status": "ok"}


# ── 部署中心（配置中心「部署」标签页：uv / node / sandbox / embedding） ──


@router.get("/deploy")
def api_get_deploy_overview():
    return config_services.deploy_overview()


@router.post("/deploy/{item}")
def api_deploy_item(item: str):
    return config_services.deploy_item(item)


# ── 磁盘维护（部署页：vhdx 空洞观测 + 一键回收 + 构建缓存清理 + 沙盒重建）──


@router.get("/deploy/disk")
def api_get_disk_status():
    return config_services.disk_status()


@router.post("/deploy/disk/compact")
def api_compact_disk():
    return config_services.compact_disk()


@router.post("/deploy/disk/prune")
def api_prune_disk():
    return config_services.prune_disk()


@router.post("/deploy/disk/rebuild")
def api_rebuild_sandbox():
    return config_services.rebuild_sandbox()


# ── 沙盒镜像源（部署页自定义，写入 settings.json 的 sandbox_registry）──
@router.get("/sandbox-registry")
def api_get_sandbox_registry():
    return config_services.get_sandbox_registry()


@router.put("/sandbox-registry")
def api_update_sandbox_registry(payload: Dict[str, Any]):
    return config_services.update_sandbox_registry(payload.get("sandbox_registry"))


# ── Markdown Files (SOUL.md / GOAL.md) ──
@router.get("/markdown/{filename}")
def api_get_markdown_file(filename: str):
    # 限制只允许读取 SOUL 和 GOAL，防止任意路径穿越漏洞
    filename = config_validation.validate_markdown_filename(filename)

    # 引入 config 中定义好的 AGENT_CORE_DIR (.purrcat/core/)
    file_path = os.path.join(AGENT_CORE_DIR, f"{filename}.md")

    # 如果文件不存在，返回空内容防报错
    if not os.path.exists(file_path):
        return {"content": ""}

    with open(file_path, "r", encoding="utf-8") as f:
        return {"content": f.read()}


@router.put("/markdown/{filename}")
def api_update_markdown_file(filename: str, payload: dict = Body(...)):
    filename = config_validation.validate_markdown_filename(filename)

    content = payload.get("content", "")

    # 同样定位到 AGENT_CORE_DIR (.purrcat/core/)
    file_path = os.path.join(AGENT_CORE_DIR, f"{filename}.md")

    # 自动创建 core 目录以防万一
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "message": f"{filename}.md saved successfully"}
    except Exception as e:
        print(f"Failed to save {filename}.md: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save {filename}.md")


# ── Info Config (Skills & Workshops) ──
@router.get("/info")
def api_get_info_config():
    """读取 .purrcat/core/info.json，提供 skills 和 workshops 列表"""
    file_path = os.path.join(AGENT_CORE_DIR, "info.json")
    if not os.path.exists(file_path):
        return {"skills": [], "workshops": []}
    return config_validation.load_json_data(file_path, {"skills": [], "workshops": []})


# ── 数据根目录（settings.json 内部管理，UI 无全局设置编辑页） ──


def _validate_data_root(value: str) -> str:
    """兼容旧入口；校验实现见 config_validation。"""
    return config_validation.validate_data_root(value)


# ── 首次启动数据盘引导 ──
@router.get("/setup-status")
def api_setup_status():
    """首启引导用：数据盘是否已配置（配置过就不再弹引导）"""
    configured = is_data_root_configured()
    return {"configured": configured, "data_root": DATA_ROOT if configured else ""}


@router.post("/setup-data-root")
def api_setup_data_root(payload: Dict[str, Any] = Body(default={})):
    return config_services.setup_data_root(payload)


@router.post("/change-data-root")
def api_change_data_root(payload: Dict[str, Any] = Body(default={})):
    return config_services.change_data_root(payload)


# ── Cron Config (cron.json) ──
@router.get("/cron")
def api_get_cron_config():
    return config_validation.load_json_data(CRON_FILE, {"jobs": []}, log_prefix="")


@router.put("/cron")
def api_update_cron_config(config: Dict[str, Any]):
    if _save_json_file(CRON_FILE, config):
        return {"status": "ok", "message": "Cron config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save cron config")


# ── Paths Meta (前端展示用：当前实际生效的各数据目录) ──
@router.get("/meta")
def api_get_config_meta():
    """返回当前正在生效的路径常量，便于前端显示给用户做参考。"""
    return {
        "PURRCAT_DIR": PURRCAT_DIR,  # ~/.purrcat（配置类目录，固定）
        "DATA_ROOT": DATA_ROOT,  # 大型数据根目录（读 settings.json data_root，重启生效）
        "BASE_DIR": BASE_DIR,  # 程序只读目录（打包后是 _MEIPASS）
        "settings_path": str(GLOBAL_CONFIG_FILE),
        "cron_path": CRON_FILE,
    }
