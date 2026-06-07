import json
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Body

# 👇 引入全局的 agent_manager
from src.agent.manager import manager as agent_manager

from src.utils.config import (
    FILE_CONFIG_PATH,
    MCP_CONFIG_PATH,
    MEMORY_CONFIG_PATH,
    MODEL_CONFIG_PATH,
    SENSOR_CONFIG_PATH,
    AGENT_CORE_DIR,
    get_file_config,
    get_mcp_config,
    get_memory_config,
    get_model_config,
    get_sensor_config,
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
        return {"status": "ok", "message": "Model config updated and reloaded successfully"}
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


# ── Memory Config ──
@router.get("/memory")
def api_get_memory_config():
    return get_memory_config()


@router.put("/memory")
def api_update_memory_config(config: Dict[str, Any]):
    if _save_json_file(MEMORY_CONFIG_PATH, config):
        return {"status": "ok", "message": "Memory config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save memory config")


# ── MCP Config ──
@router.get("/mcp")
def api_get_mcp_config():
    return get_mcp_config()


@router.put("/mcp")
def api_update_mcp_config(config: Dict[str, Any]):
    if _save_json_file(MCP_CONFIG_PATH, config):
        return {"status": "ok", "message": "MCP config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save MCP config")


# ── Markdown Files (SOUL.md / SOLO.md) ──
@router.get("/markdown/{filename}")
def api_get_markdown_file(filename: str):
    # 限制只允许读取 SOUL、SOLO 和 TODO，防止任意路径穿越漏洞
    if filename not in ["SOUL", "SOLO", "TODO"]:
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
    if filename not in ["SOUL", "SOLO", "TODO"]:
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
