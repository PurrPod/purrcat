"""
ACP 词汇分发器 (server/acp/dispatch.py)

JSON-RPC 方法分发；内部事件 → ACP 词汇翻译的唯一实现在 updates.py：
- HTTP 端点（api/acp.py：鉴权薄壳）直调 handle_rpc / to_updates
- stdio 桥（sensor/bridge.py：同进程直调）共用同一函数

词汇路由器物理唯一，传输（HTTP/SSE 或 stdio）与词汇（ACP）正交。
工具/事件词汇翻译见 tool_vocab.py 与 updates.py，本模块仅做 RPC 分发与传输辅助。
"""

import base64
import datetime
import json
import mimetypes
import os
import re
import threading
import time
import uuid

from src.server.acp.sessions import get_registry, push_by_entry
from src.server.acp.updates import to_updates
from src.utils.config import AGENT_VM_DIR

__all__ = ["MAX_SENSOR_FILE_BYTES", "handle_rpc", "save_inbound_file", "to_updates"]

# stdio 单行传输的文件体积上限（原始字节），与旧 gateway 一致
MAX_SENSOR_FILE_BYTES = 20 * 1024 * 1024


def _rpc_result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _extract_prompt_text(prompt_blocks: list) -> str:
    """ACP prompt 内容块 → 纯文本注入 Agent。

    - text：正文（baseline MUST）
    - resource_link：baseline MUST，转文本引用（Agent 可用工具自行读取）
    - resource（嵌入式）：宽容兼容（未通告 embeddedContext 也不硬拒）
    - image/audio：未通告 promptCapabilities，客户端不应发送，静默忽略
    """
    parts = []
    for block in prompt_blocks or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "resource_link":
            uri = str(block.get("uri", ""))
            name = block.get("name") or uri
            parts.append(f"[引用资源] {name} ({uri})")
        elif btype == "resource":
            res = block.get("resource") or {}
            if res.get("text"):
                parts.append(f"[嵌入资源] {res.get('uri', '')}\n{res['text']}")
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


# ==== 会话词汇：session/list / session/load / session/delete ====


def _iso8601(local_str) -> str | None:
    """purrcat 本地时间串（%Y-%m-%d %H:%M:%S）→ ISO 8601 带本地时区"""
    try:
        dt = datetime.datetime.strptime(str(local_str), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo).isoformat(
            timespec="seconds"
        )
    except Exception:
        return None


def _handle_session_list(req: dict) -> dict:
    """session/list：purrcat 全部会话（index.json 极速版，按活跃时间倒序）。

    cwd 过滤/cursor 分页 v1 不做（purrcat 会话不绑定客户端工程目录）。
    """
    from src.agent.session_store import SessionStore

    sessions = []
    for sid, info in SessionStore.get_all_sessions().items():
        entry = {
            "sessionId": sid,
            "cwd": "/agent_vm",
            "title": info.get("alias") or sid,
            "updatedAt": _iso8601(info.get("updated_at")),
            "_meta": {"messageCount": info.get("messages_count", 0)},
        }
        sessions.append(entry)
    sessions.sort(key=lambda s: s.get("updatedAt") or s["sessionId"], reverse=True)
    return _rpc_result(req.get("id"), {"sessions": sessions})


# 已知系统注入事件 type（不渲染为用户消息；代码证据：hooks/sub_runner=system、
# heartbeat=system_clock、bg搜索提示=workflow_hint、task工具=task_message）
_SYSTEM_EVENT_TYPES = {
    "system",
    "system_clock",
    "workflow_hint",
    "task_message",
    "memory",
}


def _user_visible_text(content) -> str:
    """user 消息 → 真正由用户发送的文本（与 ui/ ChatShared.parseEventsContent 对齐）。

    purrcat 的 user 消息可能是 {"events":[{type,content},...]} 包装：
    - type=user            → 真人消息，渲染
    - file/skill/tool/mcp/graph-quote → 附件引用，转文本行
    - 系统注入 type（_SYSTEM_EVENT_TYPES）→ 不渲染
    - 其余 type（unknown/客户端名等）→ 渲染（旧 ACP 数据错存特征：真人输入
      曾被存为 client 名/unknown，不能因源头 bug 吞掉用户消息）
    JSON dict 但无 events 键（workflow_hint 等独立注入）→ 不渲染（与 UI 一致）
    JSON 解析失败 → 整条即用户纯文本消息（UI 的 catch 回退同款语义）
    """
    content = str(content or "")
    try:
        data = json.loads(content)
    except Exception:
        return content
    if not isinstance(data, dict):
        return content
    events = data.get("events")
    if not isinstance(events, list):
        return ""  # 独立 JSON 注入（无 events 包装）不是用户可见消息
    lines = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        etype = str(ev.get("type", "") or "")
        text = str(ev.get("content", "") or "")
        if not etype or etype in _SYSTEM_EVENT_TYPES:
            continue
        if etype.endswith("-quote") and etype.split("-", 1)[0] in (
            "file",
            "skill",
            "tool",
            "mcp",
            "graph",
        ):
            label = etype.removesuffix("-quote")
            lines.append(f"[{label}引用] {text}" if text else f"[{label}引用]")
        else:
            # user 及宽容兜底（unknown/客户端名等旧 ACP 错存的真人输入）
            lines.append(text)
    return "\n".join(line for line in lines if line)


def _replay_history(purr_sid: str) -> None:
    """session/load 的历史回放：main 分支历史 → 总线事件（复用 to_updates 翻译）。

    传输方须在调用前完成订阅（relay 先连 SSE 流再发 load；bridge 常驻订阅）。
    user 消息经 _user_visible_text 过滤（系统注入不透出，与 UI 渲染一致）。
    """
    from src.agent.session_store import SessionStore
    from src.server.acp.bus import get_bus

    for msg in SessionStore.load_session_history(purr_sid, branch_id="main"):
        role = msg.get("role")
        if role == "user":
            text = _user_visible_text(msg.get("content"))
            if text:
                get_bus().publish(purr_sid, "user_message", {"text": text})
        elif role == "assistant":
            rc = msg.get("reasoning_content")
            if rc:
                get_bus().publish(purr_sid, "agent_thought", {"text": rc})
            if msg.get("content"):
                get_bus().publish(purr_sid, "agent_message", {"text": msg["content"]})
        elif role == "tool":
            # 工具结果回放：与实时 tool_call 事件同载荷同翻译
            get_bus().publish(
                purr_sid,
                "tool_call",
                {
                    "name": msg.get("name", "tool"),
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "result": msg.get("content", ""),
                },
            )


def _handle_session_load(req: dict) -> dict:
    """session/load：绑定既有 purrcat 会话（ACP id 复用原会话 id）+ 回放历史。

    规范：回放完毕才回 result:null；mcpServers/cwd 参数 v1 忽略
    （purrcat 自有 MCP 配置，见 ACP_REFACTOR_PLAN §4.4）。
    末尾发 replay_done 终结标记（总线 FIFO，必在全部回放事件之后），
    SSE 传输方据此补响应，保证「所有 update 先于 load 响应」的规范顺序。
    """
    params = req.get("params", {})
    purr_sid = params.get("sessionId", "")
    if not purr_sid:
        return _rpc_error(req.get("id"), -32602, "sessionId required")

    from src.agent.session_store import SessionStore
    from src.server.acp.bus import get_bus

    if purr_sid not in SessionStore.get_all_sessions():
        return _rpc_error(req.get("id"), -32602, f"unknown sessionId: {purr_sid}")

    get_registry().bind(purr_sid)
    _replay_history(purr_sid)
    get_bus().publish(purr_sid, "replay_done", {})
    return _rpc_result(req.get("id"), None)


def _handle_session_delete(req: dict) -> dict:
    """session/delete：复用 AgentManager 删除语义（活跃会话拒绝，其余静默成功）"""
    params = req.get("params", {})
    sid = params.get("sessionId", "")
    if sid:
        from src.agent import delete_session

        try:
            delete_session(sid)
        except ValueError as e:
            return _rpc_error(req.get("id"), -32602, str(e))
        get_registry().drop_by_purr(sid)
    return _rpc_result(req.get("id"), {})


def _paradigm_modes() -> dict | None:
    """purrcat paradigm（Agent Loop yaml）→ ACP SessionModeState 通告"""
    try:
        from src.utils.paradigm_api import list_paradigms

        files = list_paradigms()
    except Exception:
        return None
    if not files:
        return None
    available = [{"id": f["name"], "name": f["name"]} for f in files]
    return {"currentModeId": available[0]["id"], "availableModes": available}


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
                    "loadSession": True,
                    "sessionCapabilities": {"list": {}, "delete": {}},
                    "_meta": {"purrcat.dev": {"launch_task": True}},
                },
                "agentInfo": {
                    "name": "PurrCat",
                    "title": "PurrCat",
                    "version": "0.1.0",
                },
            },
        )

    if method == "session/list":
        return _handle_session_list(req)

    if method == "session/load":
        return _handle_session_load(req)

    if method == "session/delete":
        return _handle_session_delete(req)

    if method == "session/new":
        client = (params.get("clientInfo") or {}).get("name", "unknown")
        # sensor 传 _meta.purrcat.follow_active=true：会话跟随当前活跃会话
        # （编辑器缺省 false：独立会话，排队等 idle 再 switch）
        follow = bool((params.get("_meta") or {}).get("purrcat.follow_active"))
        created = get_registry().create(client=client, follow_active=follow)
        result = {"sessionId": created["acpSessionId"]}
        if follow:
            result["_meta"] = {"purrcat.follow_active": True}
        # 模式通告：paradigm（Agent Loop）即 ACP mode（编辑器侧模式选择器数据源）
        modes = _paradigm_modes()
        if modes:
            result["modes"] = modes
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
        acp_sid = params.get("sessionId", "")
        mode_id = params.get("modeId", "")
        entry = get_registry().get(acp_sid)
        if entry is None:
            return _rpc_error(req_id, -32602, "unknown sessionId")
        get_registry().set_mode(acp_sid, mode_id)
        # 映射模式（编辑器）：mode = paradigm，热切换该会话的 Agent Loop
        # （复用 chat.py /paradigm 语义：只换循环逻辑，不动系统提示词）
        if not entry.get("follow") and mode_id:
            try:
                from src.agent.manager import AgentManager

                AgentManager().switch_paradigm(entry["purr_session_id"], mode_id)
            except ValueError as e:
                return _rpc_error(req_id, -32602, str(e))
            except Exception as e:
                return _rpc_error(req_id, -32603, f"switch paradigm failed: {e}")
        return _rpc_result(req_id, {"modeId": mode_id})

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
