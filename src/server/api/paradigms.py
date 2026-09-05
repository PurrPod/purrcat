"""PARADIGM（Agent Loop）配置文件管理 API。

约定：GET/POST/DELETE 的 {name} 均为不带 .yaml 后缀的文件名；
POST 会整体覆盖写回，天然承担“新建”与“保存”两种语义。
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from src.utils import paradigm_api as pa

router = APIRouter(prefix="/api/paradigms", tags=["Paradigms"])


@router.get("")
def list_paradigms_api() -> Dict[str, Any]:
    """列出 paradigms 目录下所有可编辑文件。"""
    try:
        files = pa.list_paradigms()
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "default": pa.DEFAULT_FILE_BASE,
        "files": files,
    }


@router.get("/{name}")
def get_paradigm_api(name: str) -> Dict[str, Any]:
    """读取某个 paradigm 的完整结构化内容（含 hooks）。"""
    try:
        data = pa.load_paradigm(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"paradigm 不存在: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"name": pa.safe_name(name), "data": data}


@router.post("/{name}")
def save_paradigm_api(name: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """整体写回（新建/保存同一接口）。body: { "data": {...} }"""
    data = body.get("data") if isinstance(body, dict) else None
    try:
        if not isinstance(data, dict):
            raise ValueError("data 必须是一个 YAML 对象")
        path = pa.save_paradigm(name, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "name": pa.safe_name(name), "path": path}


@router.delete("/{name}")
def delete_paradigm_api(name: str) -> Dict[str, Any]:
    """删除指定 paradigm（默认 PARADIGM.yaml 除外）。"""
    try:
        pa.delete_paradigm(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "name": pa._safe_name(name)}
