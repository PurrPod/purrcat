"""MCP Apps 渲染接口：取回已落盘的 App HTML/调用载荷，并代理 App 发起的工具调用。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.tool.callmcp import mcp_apps
from src.tool.callmcp.session_manager import _run_sync, load_configs, mcp_manager

router = APIRouter(prefix="/api/mcp/apps", tags=["MCP Apps"])


class AppToolCallReq(BaseModel):
    tool: str
    arguments: dict = {}


def _require_payload(app_id: str) -> dict:
    if not mcp_apps.is_legal_app_id(app_id):
        raise HTTPException(status_code=400, detail="非法的 App id")
    payload = mcp_apps.load_payload(app_id)
    if not payload:
        raise HTTPException(status_code=404, detail="App 不存在或已被清理")
    return payload


@router.get("/{app_id}/html", response_class=HTMLResponse)
def get_app_html(app_id: str):
    """返回 App 的单文件 HTML（由 iframe 直接加载）。"""
    _require_payload(app_id)
    html = mcp_apps.load_html(app_id)
    if html is None:
        raise HTTPException(status_code=404, detail="App HTML 不存在")
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


@router.get("/{app_id}/payload")
def get_app_payload(app_id: str):
    """返回 App 初始化所需的参数与工具调用结果。"""
    payload = _require_payload(app_id)
    return {"id": app_id, **payload}


async def _call_from_app_async(server_name: str, tool_name: str, arguments: dict):
    config = load_configs().get(server_name)
    if not config:
        raise RuntimeError(f"MCP Server '{server_name}' 未配置")
    session = await mcp_manager.get_session(server_name, config)
    result = await session.call_tool(tool_name, arguments or {})
    dumped = result.model_dump(mode="json", exclude_none=True)
    payload = {"content": dumped.get("content", []), "isError": bool(result.isError)}
    if dumped.get("structuredContent") is not None:
        payload["structuredContent"] = dumped["structuredContent"]
    if dumped.get("meta") is not None:
        payload["_meta"] = dumped["meta"]
    return payload


@router.post("/{app_id}/call")
def call_tool_from_app(app_id: str, req: AppToolCallReq):
    """代理 App 的 tools/call：只允许调用该 App 所属 server 的工具。"""
    payload = _require_payload(app_id)
    server_name = str(payload.get("server") or "")
    if not req.tool:
        raise HTTPException(status_code=400, detail="缺少 tool 名称")
    try:
        return _run_sync(_call_from_app_async, server_name, req.tool, req.arguments)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
