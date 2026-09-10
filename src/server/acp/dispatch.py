"""
ACP 词汇分发器 (server/acp/dispatch.py)

JSON-RPC 方法分发 + 内部事件 → ACP 词汇翻译的**唯一实现**：
- HTTP 端点（api/acp.py：鉴权薄壳）直调 handle_rpc / to_updates
- stdio 桥（sensor/bridge.py：同进程直调）共用同一函数

词汇路由器物理唯一，传输（HTTP/SSE 或 stdio）与词汇（ACP）正交。
"""

import base64
import itertools
import mimetypes
import os
import re
import threading
import time
import uuid

from src.server.acp.sessions import get_registry, push_by_entry
from src.utils.config import AGENT_VM_DIR

# stdio 单行传输的文件体积上限（原始字节），与旧 gateway 一致
MAX_SENSOR_FILE_BYTES = 20 * 1024 * 1024

_tool_call_counter = itertools.count(1)
_msg_counter = itertools.count(1)


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


def save_inbound_file(source: str, params: dict) -> dict | None:
    """文件落盘：base64 解码后写 AGENT_VM_DIR/sensor/files/<source>/。
    返回 {"path", "mime", "size_h"}；失败 None。旧 observe type=file 同逻辑。"""
    try:
        data = base64.b64decode(params.get("content_b64") or "")
    except Exception as e:
        print(f"❌ [ACP] {source} 上传文件 base64 解码失败: {e}")
        return None
    if not data:
        return None
    if len(data) > MAX_SENSOR_FILE_BYTES:
        print(f"⚠️ [ACP] {source} 上传文件超过 20MB 上限，已丢弃")
        return None

    # 文件名只保留 basename 并清洗 Windows 非法字符，防路径穿越
    raw_name = str(params.get("name") or "file")
    file_name = (
        re.sub(r'[<>:"/\\|?*]', "_", os.path.basename(raw_name)).strip("._") or "file"
    )
    mime = params.get("mime") or "application/octet-stream"
    if not os.path.splitext(file_name)[1]:
        ext = mimetypes.guess_extension(mime)
        if ext:
            file_name += ext

    target_dir = os.path.join(AGENT_VM_DIR, "sensor", "files", source)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, f"{int(time.time() * 1000)}_{file_name}")
    with open(target, "wb") as f:
        f.write(data)

    size = len(data)
    size_h = (
        f"{size / 1024 / 1024:.1f}MB" if size >= 1024 * 1024 else f"{size / 1024:.0f}KB"
    )
    return {
        "path": f"/agent_vm/sensor/files/{source}/{os.path.basename(target)}",
        "mime": mime,
        "size_h": size_h,
    }


def _handle_prompt(req: dict) -> dict:
    """session/prompt：异步注入（按映射模式分流），立即返回受理凭据。

    最终 stopReason 不在本次响应给出 —— 由事件流的 turn_end 事件补，
    传输方（SSE relay / stdio 桥）据此回 JSON-RPC 响应。
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
        target=push_by_entry,
        args=(entry, text),
        kwargs={"source": entry.get("client") or "acp"},
        daemon=True,
    ).start()
    return _rpc_result(req.get("id"), {"accepted": True, "promptId": prompt_id})


def _handle_launch_task(req: dict) -> dict:
    """_purrcat/launch_task 扩展方法：后台线程拉起 Harness Task 图谱
    （时钟 sensor 的触发语义，与 sensor/manager.py 旧路径一致）"""
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


def handle_rpc(req: dict) -> dict:
    """JSON-RPC 2.0 单条分发（v1 不做 batch）。HTTP 端点与 stdio 桥共用。"""
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
        # sensor 传 _meta.purrcat.follow_active=true：会话跟随当前活跃会话
        # （编辑器缺省 false：独立会话，排队等 idle 再 switch）
        follow = bool((params.get("_meta") or {}).get("purrcat.follow_active"))
        created = get_registry().create(client=client, follow_active=follow)
        result = {"sessionId": created["acpSessionId"]}
        if follow:
            result["_meta"] = {"purrcat.follow_active": True}
        return _rpc_result(req_id, result)

    if method == "session/prompt":
        return _handle_prompt(req)

    if method == "session/cancel":
        # ACP 规范：cancel 是通知（无 id 无响应）。HTTP 层天然请求-响应，
        # 这里返回受理标记；传输方负责不向客户端回写任何响应。
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

    if method == "_purrcat/upload_file":
        # stdio sensor → agent 文件上传（替代旧 observe type=file）。
        # source 缺省 acp；stdio 桥调用前会注入 sensor 名。
        source = (params.get("_meta") or {}).get("source") or "acp"
        saved = save_inbound_file(source, params)
        if saved is None:
            return _rpc_error(req_id, -32602, "invalid/empty file payload")
        return _rpc_result(req_id, {"path": saved["path"]})

    return _rpc_error(req_id, -32601, f"method not found: {method}")


# ==== 内部事件 → ACP 词汇翻译（SSE 与 stdio 桥共用） ====


def _upd(acp_sid: str, update: dict) -> dict:
    """组装一条 session/update 通知载荷"""
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": acp_sid, "update": update},
    }


def to_updates(envelope: dict) -> list[dict]:
    """内部事件信封 → update 载荷列表（空列表 = 不透出）。

    规范词汇映射（v1 事件粒度）：
    - agent_message → agent_message_chunk（带 messageId，一条 assistant 消息一个 id）
    - agent_thought → agent_thought_chunk
    - tool_call    → tool_call(pending) + tool_call_update(completed) 成对
                     （规范要求初始 tool_call 无内容、状态流转走 update）
    - turn_end     → 自定义终结信号（传输方据此回 session/prompt 响应，stopReason）
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
        # ACP 无直接对应；自定义事件透出，传输方可忽略
        return [{"phase": data.get("phase", "idle")}]

    if etype == "turn_end":
        return [{"stopReason": data.get("stopReason", "end_turn")}]

    return []
