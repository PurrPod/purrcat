"""
ACP 网关 HTTP 端点 (server/api/acp.py)

外部频道（Zed 转接 sensor / HTTP 版 sensor）的传输入口（鉴权薄壳）：
- POST /acp/rpc    JSON-RPC 分发（直调 server/acp/dispatch.py）
- GET  /acp/stream  SSE 事件流（session/update 系 + turn_end）
- POST /acp/file    multipart 文件上传（落 agent_vm）
- GET  /acp/file    sandbox 路径受限下载

词汇分发与翻译的唯一实现在 dispatch.py；stdio 版 sensor 由
sensor/bridge.py 同进程直调 dispatch，不经本端点。
"""

import asyncio
import json
import os
import re
import time

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.server.acp.bus import get_bus
from src.server.acp.dispatch import handle_rpc, to_updates
from src.server.acp.sessions import get_registry
from src.utils.config import AGENT_VM_DIR, get_acp_token

router = APIRouter(prefix="/acp", tags=["ACP Gateway"])

# SSE 心跳间隔（秒）
_SSE_KEEPALIVE = 15


def verify_token(x_purrcat_token: str = Header(default="")):
    """ACP 网关本地鉴权：token 文件在 ~/.purrcat/acp_token"""
    if x_purrcat_token != get_acp_token():
        raise HTTPException(status_code=401, detail="invalid ACP token")


@router.post("/rpc")
def acp_rpc(req: dict, _: str = Depends(verify_token)):
    """JSON-RPC 2.0 单条分发（v1 不做 batch）——直调 dispatch"""
    return handle_rpc(req)


# ==== SSE 事件流：内部事件 → ACP 词汇（to_updates 唯一实现于 dispatch） ====


@router.get("/stream")
async def acp_stream(session: str, _: str = Depends(verify_token)):
    """SSE：按 ACP session 订阅对应 purrcat 会话的事件流"""
    entry = get_registry().get(session)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown sessionId: {session}")
    purr_sid = entry["purr_session_id"]

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    unsubscribe = get_bus().subscribe(
        purr_sid, callback=queue.put_nowait, loop=loop
    )

    async def _gen():
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                for payload in to_updates(envelope):
                    is_update = payload.get("method") == "session/update"
                    if is_update:
                        # update 载荷里回填 ACP sessionId（信封里是内部 purrcat 会话）
                        payload["params"]["sessionId"] = session
                    elif "stopReason" in payload:
                        payload["promptId"] = entry.get("last_prompt_id", "")
                    event_name = "update" if is_update else (
                        "turn_end" if "stopReason" in payload else "phase"
                    )
                    yield f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            unsubscribe()

    return StreamingResponse(_gen(), media_type="text/event-stream")


# ==== 文件传输（传输层能力，不进词汇表）====

_ACP_FILE_DIR = os.path.join(AGENT_VM_DIR, "sensor", "files", "acp")


def _sanitize_name(raw: str) -> str:
    """只保留 basename 并清洗 Windows 非法字符，防路径穿越（同旧网关逻辑）"""
    name = re.sub(r'[<>:"/\\|?*]', "_", os.path.basename(raw or "file")).strip("._")
    return name or "file"


@router.post("/file")
async def acp_upload_file(
    file: UploadFile, session: str = "", _: str = Depends(verify_token)
):
    """multipart 上传：落 agent_vm/sensor/files/acp/，返回 sandbox 路径供 prompt 引用"""
    if not get_registry().get(session):
        raise HTTPException(status_code=404, detail=f"unknown sessionId: {session}")

    os.makedirs(_ACP_FILE_DIR, exist_ok=True)
    name = _sanitize_name(file.filename)
    target = os.path.join(_ACP_FILE_DIR, f"{int(time.time() * 1000)}_{name}")
    with open(target, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    return {
        "path": f"/agent_vm/sensor/files/acp/{os.path.basename(target)}",
        "size": os.path.getsize(target),
    }


@router.get("/file")
def acp_download_file(path: str, _: str = Depends(verify_token)):
    """下载 sandbox 文件（仅允许 /agent_vm 前缀，防任意路径读取）"""
    from src.utils.path import convert_sandbox_path

    if not path.startswith("/agent_vm/"):
        raise HTTPException(status_code=400, detail="only /agent_vm paths allowed")
    host_path = os.path.realpath(convert_sandbox_path(path))
    vm_root = os.path.realpath(AGENT_VM_DIR)
    if not host_path.startswith(vm_root + os.sep) or not os.path.isfile(host_path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(host_path)
