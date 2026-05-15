import os
import json
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from src.utils.config import (
    MODEL_CONFIG_PATH,
    SENSOR_CONFIG_PATH,
    FILE_CONFIG_PATH,
    MEMORY_CONFIG_PATH,
    MCP_CONFIG_PATH,
    get_model_config,
    get_sensor_config,
    get_file_config,
    get_memory_config,
    get_mcp_config,
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
        return {"status": "ok", "message": "Model config updated successfully"}
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
