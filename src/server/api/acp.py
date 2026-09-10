"""
ACP 网关 HTTP 端点 (server/api/acp.py)

外部频道（Zed 转接 sensor / HTTP 版 sensor）的统一词汇入口：
- POST /acp/rpc    JSON-RPC 分发（initialize / newSession / session/prompt / ...）
- GET  /acp/stream  SSE 事件流（session/update 系 + turn_end）
- POST /acp/file    multipart 文件上传（落 agent_vm）
- GET  /acp/file    sandbox 路径受限下载

鉴权：X-PurrCat-Token 头 == ~/.purrcat/acp_token 内容。
stdio 版 sensor 不走本端点，由 Manager 同进程直调 sessions/bus（Phase 3）。
"""

import asyncio
import itertools
import json
import os
import re
import threading
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.server.acp.bus import get_bus
from src.server.acp.sessions import ensure_active_and_push, get_registry
from src.utils.config import AGENT_VM_DIR, get_acp_token

router = APIRouter(prefix="/acp", tags=["ACP Gateway"])

# SSE 心跳间隔（秒）
_SSE_KEEPALIVE = 15


def verify_token(x_purrcat_token: str = Header(default="")):
    """ACP 网关本地鉴权：token 文件在 ~/.purrcat/acp_token"""
    if x_purrcat_token != get_acp_token():
        raise HTTPException(status_code=401, detail="invalid ACP token")


def _rpc_result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _extract_prompt_text(prompt_blocks: list) -> str:
    """ACP prompt 内容块（[{type:"text",text:...}]）→ 纯文本"""
    parts = []
    for block in prompt_blocks or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p)


def _handle_prompt(req: dict) -> dict:
    """session/prompt：异步注入（排队等 idle），立即返回受理凭据。

    最终 stopReason 不在本次响应给出 —— 由 SSE 的 turn_end 事件补，
    转接方据此回 JSON-RPC 响应给编辑器。
    """
    params = req.get("params", {})
    acp_sid = params.get("sessionId", "")
    text = _extract_prompt_text(params.get("prompt"))
    if not text:
        return _rpc_error(req.get("id"), -32602, "empty prompt")

    entry = get_registry().get(acp_sid)
    if entry is None:
        return _rpc_error(req.get("id"), -32602, f"unknown sessionId: {acp_sid}")

    prompt_id = uuid.uuid4().hex
    get_registry().mark_prompt(acp_sid, prompt_id)
    threading.Thread(
        target=ensure_active_and_push,
        args=(entry["purr_session_id"], text),
        kwargs={"source": "acp"},
        daemon=True,
    ).start()
    return _rpc_result(req.get("id"), {"accepted": True, "promptId": prompt_id})


def _handle_launch_task(req: dict) -> dict:
    """purrcat/launch_task 扩展方法：后台线程拉起 Harness Task 图谱

    （与 sensor/manager.py 收到时钟触发后的启动逻辑一致）
    """
    params = req.get("params", {})
    graph_name = params.get("graph_name")
    if not graph_name:
        return _rpc_error(req.get("id"), -32602, "graph_name required")

    inputs = params.get("inputs", {})
    title = params.get("title", "acp_task")

    def _run_bg_task():
        import asyncio
        from src.harness.process import Task

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            task = Task(task_name=title, inputs=inputs, graph_name=graph_name)
            loop.run_until_complete(task.run())
        except Exception as e:
            print(f"❌ [ACP] 后台任务执行崩溃: {e}")

    threading.Thread(target=_run_bg_task, daemon=True).start()
    return _rpc_result(req.get("id"), {"launched": True})


@router.post("/rpc")
def acp_rpc(req: dict, _: str = Depends(verify_token)):
    """JSON-RPC 2.0 单条分发（v1 不做 batch）"""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return _rpc_result(
            req_id,
            {
                "protocolVersion": 1,
                "agentCapabilities": {
                    "loadSession": False,
                    "_meta": {"purrcat.dev": {"launch_task": True}},
                },
                "agentInfo": {"name": "PurrCat", "version": "0.1.0"},
            },
        )

    if method == "session/new":
        client = (params.get("clientInfo") or {}).get("name", "unknown")
        created = get_registry().create(client=client)
        return _rpc_result(req_id, {"sessionId": created["acpSessionId"]})

    if method == "session/prompt":
        return _handle_prompt(req)

    if method == "session/cancel":
        # ACP 规范：cancel 是通知（无 id 无响应）。HTTP 层天然请求-响应，
        # 这里返回受理标记；转接脚本负责不向编辑器回写任何响应。
        from src.agent import agent_force_interrupt

        agent_force_interrupt()
        return _rpc_result(req_id, {"accepted": True})

    if method == "session/set_mode":
        ok = get_registry().set_mode(params.get("sessionId", ""), params.get("modeId", ""))
        if not ok:
            return _rpc_error(req_id, -32602, "unknown sessionId")
        return _rpc_result(req_id, {"modeId": params.get("modeId", "")})

    if method == "_purrcat/launch_task":
        return _handle_launch_task(req)

    return _rpc_error(req_id, -32601, f"method not found: {method}")


# ==== SSE 事件流：内部事件 → ACP 词汇 ====

_tool_call_counter = itertools.count(1)
_msg_counter = itertools.count(1)


def _upd(acp_sid: str, update: dict) -> dict:
    """组装一条 session/update 通知载荷"""
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": acp_sid, "update": update},
    }


def _to_updates(envelope: dict) -> list[dict]:
    """内部事件信封 → SSE data 载荷列表（空列表 = 不透出）。

    规范词汇映射（v1 事件粒度）：
    - agent_message → agent_message_chunk（带 messageId，一条 assistant 消息一个 id）
    - agent_thought → agent_thought_chunk
    - tool_call    → tool_call(pending) + tool_call_update(completed) 成对
                     （规范要求初始 tool_call 无内容、状态流转走 update）
    - turn_end     → 自定义终结信号（转接方据此回 session/prompt 响应，stopReason）
    """
    etype = envelope["type"]
    data = envelope.get("data", {})

    if etype == "agent_message":
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "agent_message_chunk",
                    "messageId": f"msg_{next(_msg_counter)}",
                    "content": {"type": "text", "text": data.get("text", "")},
                },
            )
        ]

    if etype == "agent_thought":
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "agent_thought_chunk",
                    "content": {"type": "text", "text": data.get("text", "")},
                },
            )
        ]

    if etype == "tool_call":
        tcid = f"acp_{next(_tool_call_counter)}"
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "tool_call",
                    "toolCallId": tcid,
                    "title": data.get("name", "tool"),
                    "kind": "execute",
                    "status": "pending",
                },
            ),
            _upd(
                "",
                {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": tcid,
                    "status": "completed",
                    "content": [
                        {
                            "type": "text",
                            "text": data.get("snip", ""),
                        }
                    ],
                },
            ),
        ]

    if etype == "phase":
        # ACP 无直接对应；自定义事件透出，转接方可忽略
        return [{"phase": data.get("phase", "idle")}]

    if etype == "turn_end":
        return [{"stopReason": data.get("stopReason", "end_turn")}]

    return []


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
                for payload in _to_updates(envelope):
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
