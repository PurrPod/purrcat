import json
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Body

# 👇 引入全局的 agent_manager
from src.agent.manager import manager as agent_manager

from src.utils.config import (
    APP_CONFIG_PATH,
    FILE_CONFIG_PATH,
    MCP_CONFIG_PATH,
    MODEL_CONFIG_PATH,
    SENSOR_CONFIG_PATH,
    AGENT_CORE_DIR,
    GLOBAL_CONFIG_FILE,
    CRON_FILE,
    get_app_config,
    get_file_config,
    get_mcp_config,
    get_model_config,
    get_sensor_config,
    get_global_settings,
    PURRCAT_DIR,
    DATA_ROOT,
    BASE_DIR,
)

router = APIRouter(prefix="/api/config", tags=["Configuration"])


def _save_json_file(file_path: str, data: Dict[str, Any]) -> bool:
    """通用的 JSON 写入方法"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config API] 保存配置文件失败 {file_path}: {e}")
        return False


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
    if _save_json_file(SENSOR_CONFIG_PATH, config):
        return {"status": "ok", "message": "Sensor config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save sensor config")


@router.post("/sensor/reload")
def api_reload_sensor_manager():
    """停止所有运行中的 Sensor 进程，并重新读取配置拉起启用状态的 Sensor"""
    try:
        from src.sensor.manager import get_manager

        manager = get_manager()
        manager.stop_all()  # 杀死旧进程
        manager.load_and_start_all()  # 重新读取 activate_sensor.json 并拉起
        return {"status": "ok", "message": "Sensors reloaded successfully"}
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"热重启失败: {str(e)}")


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


# ── App Config ──
@router.get("/app")
def api_get_app_config():
    return get_app_config()


@router.put("/app")
def api_update_app_config(config: Dict[str, Any]):
    if _save_json_file(APP_CONFIG_PATH, config):
        return {"status": "ok", "message": "App config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save app config")


# ── Markdown Files (SOUL.md / GOAL.md) ──
@router.get("/markdown/{filename}")
def api_get_markdown_file(filename: str):
    # 限制只允许读取 SOUL 和 GOAL，防止任意路径穿越漏洞
    if filename not in ["SOUL", "GOAL"]:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # 引入 config 中定义好的 AGENT_CORE_DIR (.purrcat/core/)
    file_path = os.path.join(AGENT_CORE_DIR, f"{filename}.md")

    # 如果文件不存在，返回空内容防报错
    if not os.path.exists(file_path):
        return {"content": ""}

    with open(file_path, "r", encoding="utf-8") as f:
        return {"content": f.read()}


@router.put("/markdown/{filename}")
def api_update_markdown_file(filename: str, payload: dict = Body(...)):
    if filename not in ["SOUL", "GOAL"]:
        raise HTTPException(status_code=400, detail="Invalid filename")

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
    try:
        file_path = os.path.join(AGENT_CORE_DIR, "info.json")
        if not os.path.exists(file_path):
            return {"skills": [], "workshops": []}
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config API] 读取 info.json 失败: {e}")
        return {"skills": [], "workshops": []}


# ── Global Settings (settings.json) ──
@router.get("/settings")
def api_get_settings():
    """读取全局 settings.json，含 data_root、sandbox_engine 等。
    文件不存在或为空时，返回带默认字段的结构，方便前端直接编辑。"""
    settings = get_global_settings()
    # 兜底：给前端一些默认占位字段，用户可以直接填
    defaults = {
        "data_root": "",      # 空字符串 = 使用 PURRCAT_DIR
        "sandbox_engine": "docker",
    }
    for k, v in defaults.items():
        if k not in settings:
            settings[k] = v
    return settings


@router.put("/settings")
def api_update_settings(config: Dict[str, Any]):
    """整体覆盖保存 settings.json。保存成功后 data_root 要重启才会生效（_get_data_root 仅模块加载时读一次）。"""
    # data_root 为空字符串时，视为「使用默认 PURRCAT_DIR」，保存时去掉该键，下次加载即 fallback
    save_data = {k: v for k, v in config.items() if not (k == "data_root" and (v == "" or v is None))}
    if _save_json_file(str(GLOBAL_CONFIG_FILE), save_data):
        return {"status": "ok", "message": "Settings saved. data_root will take effect after restart."}
    raise HTTPException(status_code=500, detail="Failed to save settings")


# ── Cron Config (cron.json) ──
@router.get("/cron")
def api_get_cron_config():
    if not os.path.exists(CRON_FILE):
        return {"jobs": []}
    try:
        with open(CRON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"jobs": []}


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
        "PURRCAT_DIR": PURRCAT_DIR,     # ~/.purrcat（配置类目录，固定）
        "DATA_ROOT": DATA_ROOT,         # 大型数据根目录（读 settings.json data_root，重启生效）
        "BASE_DIR": BASE_DIR,           # 程序只读目录（打包后是 _MEIPASS）
        "settings_path": str(GLOBAL_CONFIG_FILE),
        "cron_path": CRON_FILE,
    }
