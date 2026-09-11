"""
ACP 词汇分发器 (server/acp/dispatch.py)

JSON-RPC 方法分发 + 内部事件 → ACP 词汇翻译的**唯一实现**：
- HTTP 端点（api/acp.py：鉴权薄壳）直调 handle_rpc / to_updates
- stdio 桥（sensor/bridge.py：同进程直调）共用同一函数

词汇路由器物理唯一，传输（HTTP/SSE 或 stdio）与词汇（ACP）正交。
"""

import base64
import datetime
import itertools
import json
import mimetypes
import os
import re
import threading
import time
import uuid

from src.server.acp.sessions import get_registry, push_by_entry
from src.tool.utils.token_limit import count_tokens, truncate_to_tokens
from src.utils.config import AGENT_VM_DIR

# stdio 单行传输的文件体积上限（原始字节），与旧 gateway 一致
MAX_SENSOR_FILE_BYTES = 20 * 1024 * 1024

# 单条 update 透出的内容 token 上限（工具结果/回放消息统一截断，
# 复用共享 token 工具，见工程约定「token 限额一律走共享工具」）
_UPDATE_TOKEN_LIMIT = 2000

_tool_call_counter = itertools.count(1)
_msg_counter = itertools.count(1)


def _rpc_result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _truncate_update(text) -> str:
    """update 内容按 token 上限截断（超限截断，不异常）"""
    if not text:
        return ""
    text = str(text)
    try:
        if count_tokens(text) <= _UPDATE_TOKEN_LIMIT:
            return text
        return truncate_to_tokens(text, _UPDATE_TOKEN_LIMIT)
    except Exception:
        return text[:8000]


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


# ==== 工具词汇：purrcat 工具 → ACP ToolKind/标题/locations ====

# ToolKind 枚举：read/edit/delete/move/search/execute/think/fetch/other
_TOOL_KIND = {
    "Bash": "execute",
    "ComputerUse": "execute",
    "BrainStorm": "think",
    "Memo": "think",
    "Request": "fetch",
    "Fetch": "fetch",
    "Search": "search",
    "CallMCP": "other",
    "Cron": "other",
    "Task": "other",
    "KernelUpgrade": "other",
}

# FileSystem 按 action 细分（schema 枚举：list/read/edit/write/search/glob/move/copy/delete/undo）
_FS_KIND = {
    "list": "read",
    "read": "read",
    "edit": "edit",
    "write": "edit",
    "search": "search",
    "glob": "search",
    "move": "move",
    "copy": "move",
    "delete": "delete",
    "undo": "other",
}


def _tool_kind(name: str, args) -> str:
    """工具名+参数 → ToolKind（编辑器据此选图标/展示形态）"""
    if name == "FileSystem" and isinstance(args, dict):
        return _FS_KIND.get(str(args.get("action", "")), "other")
    return _TOOL_KIND.get(name, "other")


def _tool_title(name: str, args) -> str:
    """人可读标题：工具名 + 关键参数摘要"""
    if isinstance(args, dict):
        if name == "FileSystem":
            action = str(args.get("action", "") or "fs")
            path = str(args.get("path", "") or args.get("destination", ""))
            base = os.path.basename(path.replace("\\", "/")) if path else ""
            return f"FileSystem {action} {base}".strip()
        if name == "Bash":
            return f"Bash {str(args.get('command', ''))[:60]}".strip()
        if name == "Search":
            return f"Search {str(args.get('query', ''))[:40]}".strip()
        if name == "CallMCP":
            return f"CallMCP {str(args.get('server_name', ''))[:30]}".strip()
        if name == "Memo":
            action = str(args.get("action", "") or "memo")
            if action == "search":
                q = (args.get("query") or {}).get("prompt", "") if isinstance(
                    args.get("query"), dict
                ) else ""
                return f"Memo search {str(q)[:40]}".strip()
            return f"Memo {action}".strip()
    return name


def _tool_locations(name: str, args) -> list:
    """follow-the-agent：涉及文件的工具报 locations（宿主机绝对路径）"""
    if name != "FileSystem" or not isinstance(args, dict):
        return []
    path = args.get("path") or args.get("destination")
    if not path:
        return []
    try:
        from src.utils.path import convert_sandbox_path

        return [{"path": convert_sandbox_path(str(path))}]
    except Exception:
        return []


def _tool_raw(args) -> dict | None:
    """rawInput：参数对象原样透出（超 token 预算则省略，防撑爆编辑器）"""
    if not isinstance(args, dict) or not args:
        return None
    try:
        if count_tokens(json.dumps(args, ensure_ascii=False)) <= _UPDATE_TOKEN_LIMIT:
            return args
    except Exception:
        pass
    return None


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
    sessions.sort(
        key=lambda s: s.get("updatedAt") or s["sessionId"], reverse=True
    )
    return _rpc_result(req.get("id"), {"sessions": sessions})


# 已知系统注入事件 type（不渲染为用户消息；代码证据：hooks/sub_runner=system、
# heartbeat=system_clock、bg搜索提示=workflow_hint、task工具=task_message）
_SYSTEM_EVENT_TYPES = {"system", "system_clock", "workflow_hint", "task_message", "memory"}


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
    return "\n".join(l for l in lines if l)


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
                "agentInfo": {"name": "PurrCat", "title": "PurrCat", "version": "0.1.0"},
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
    - user_message → user_message_chunk（session/load 回放专用）
    - tool_call    → tool_call(pending) + tool_call_update(in_progress)
                     + tool_call_update(completed/failed+content) 三段
                     （规范要求初始 tool_call 无内容、状态流转走 update；
                     ToolCallContent 须包 {"type":"content","content":{...}}）
    - usage        → usage_update（used=window_token，size=模型上限）
    - turn_end     → session_info_update(updatedAt) + 自定义终结信号
                     （传输方据 turn_end 回 session/prompt 响应，stopReason）
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
                    "content": {
                        "type": "text",
                        "text": _truncate_update(data.get("text", "")),
                    },
                },
            )
        ]

    if etype == "agent_thought":
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "agent_thought_chunk",
                    "content": {
                        "type": "text",
                        "text": _truncate_update(data.get("text", "")),
                    },
                },
            )
        ]

    if etype == "user_message":
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "user_message_chunk",
                    "messageId": f"msg_{next(_msg_counter)}",
                    "content": {
                        "type": "text",
                        "text": _truncate_update(data.get("text", "")),
                    },
                },
            )
        ]

    if etype == "tool_call":
        name = data.get("name", "tool")
        args = data.get("arguments")
        raw_result = data.get("result", "")
        # 结果解包：dispatch_tool 统一封包 {"content": 正文, "metadata": {type, snip}}
        # → 编辑器看 content 本体（不带 JSON 噪音）；宽容兼容裸 error dict / 纯文本
        try:
            parsed = json.loads(raw_result) if raw_result else None
        except Exception:
            parsed = None
        if (
            isinstance(parsed, dict)
            and isinstance(parsed.get("metadata"), dict)
            and "content" in parsed
        ):
            body = str(parsed.get("content", "") or "")
            raw_output = parsed
            status = (
                "failed" if parsed["metadata"].get("type") == "error" else "completed"
            )
        elif isinstance(parsed, dict):
            body = raw_result
            raw_output = parsed
            status = "failed" if parsed.get("error") else "completed"
        else:
            body = str(raw_result or "")
            raw_output = None
            status = "completed"

        tcid = f"acp_{next(_tool_call_counter)}"
        call = {
            "sessionUpdate": "tool_call",
            "toolCallId": tcid,
            "title": _tool_title(name, args),
            "kind": _tool_kind(name, args),
            "status": "pending",
        }
        locations = _tool_locations(name, args)
        if locations:
            call["locations"] = locations
        raw_input = _tool_raw(args)
        if raw_input is not None:
            call["rawInput"] = raw_input

        update = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": tcid,
            "status": status,
            "content": [
                {
                    "type": "content",
                    "content": {"type": "text", "text": _truncate_update(body)},
                }
            ],
        }
        if isinstance(raw_output, dict):
            update["rawOutput"] = raw_output  # schema 类型为 object，仅 dict 形态透出

        return [
            _upd("", call),
            _upd("", {"sessionUpdate": "tool_call_update", "toolCallId": tcid, "status": "in_progress"}),
            _upd("", update),
        ]

    if etype == "usage":
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "usage_update",
                    "used": data.get("used", 0),
                    "size": data.get("size", 0),
                },
            )
        ]

    if etype == "phase":
        # ACP 无直接对应；自定义事件透出，传输方可忽略
        return [{"phase": data.get("phase", "idle")}]

    if etype == "replay_done":
        # session/load 回放终结标记（SSE 侧据补 load 响应；stdio 桥同步天然有序）
        return [{"replayDone": True}]

    if etype == "turn_end":
        # 回应 prompt 前先同步会话元数据（规范：所有 update 必须先于 prompt 响应）
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "session_info_update",
                    "updatedAt": datetime.datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds"),
                },
            ),
            {"stopReason": data.get("stopReason", "end_turn")},
        ]

    return []
