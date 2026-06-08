"""Server API - Request 审批请求接口"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 直接从工具层的高内聚 api 里引入逻辑
from src.tool.request.api import get_pending_requests, resolve_request, get_resolved_requests, delete_request

router = APIRouter(prefix="/api/requests", tags=["Agent Requests"])


class ResolveRequestReq(BaseModel):
    approved: bool = False
    feedback: str = ""
    ignore: bool = False  # 标志是否静默忽略


@router.get("")
def list_pending_requests_api():
    """获取前端需要弹窗提示的所有待处理请求"""
    try:
        return get_pending_requests()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{req_id}/resolve")
def resolve_request_api(req_id: str, payload: ResolveRequestReq):
    """前端点同意、拒绝或忽略时调用"""
    try:
        result = resolve_request(
            req_id=req_id,
            approved=payload.approved,
            feedback=payload.feedback,
            ignore=payload.ignore,
        )
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolved")
def list_resolved_requests_api():
    """获取所有已处理完毕的请求"""
    try:
        return get_resolved_requests()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{req_id}")
def delete_request_api(req_id: str):
    """彻底删除某个请求记录"""
    try:
        if delete_request(req_id):
            return {"status": "success", "message": "请求已移除"}
        raise HTTPException(status_code=404, detail="请求未找到")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
