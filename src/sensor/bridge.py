"""
ACP stdio 桥 (sensor/bridge.py)

Manager 拉起的 ACP 方言 sensor 子进程 ↔ dispatch 的同进程直调桥：
- 入向：sensor stdout 的 JSON-RPC 行 → dispatch.handle_rpc → 响应写回 stdin
  （upload_file 调用前注入 sensor 名作落盘 source）
- 出向：bus 全订阅（follow 模式，单活跃会话模型下 ≈ 活跃会话）→
  to_updates 逐行写 stdin；turn_end 回写持住的 prompt 响应（stopReason）
- 文件出向：agent 消息提及本地文件路径时，推 `_purrcat/file` 通知
  （替代旧 express_file，sensor 自行发送）

与 relay（scripts/acp_relay.py）同机制但零网络：这里是进程内函数调用。
"""

import base64
import json
import mimetypes
import os
import threading

from src.server.acp.bus import get_bus
from src.server.acp.dispatch import MAX_SENSOR_FILE_BYTES, handle_rpc, to_updates
from src.server.acp.sessions import get_registry
from src.sensor.gateway import extract_file_paths


class AcpSensorBridge:
    """一个 ACP 方言 sensor 子进程一座桥。生命周期 = 监听线程（进程死则桥亡）。"""

    def __init__(self, name: str, stdin_pipe, tool_detail: bool = False):
        self.name = name
        self.stdin = stdin_pipe
        # false 时只透传正文（agent_message_chunk + turn_end），工具/思考细节不发
        # ——与旧 RemoteSensorProxy.tool_detail 语义一致
        self.tool_detail = tool_detail
        self.acp_sid = ""  # session/new 响应时记住（sensor 单进程长持一个会话）
        self._alive = True
        self._lock = threading.Lock()  # 串行化 stdin 写（bus 回调 vs 请求响应）
        self._pending = {}  # promptId -> req_id（持住的 session/prompt）
        self._pending_order = []  # FIFO：turn_end 依序回写
        self._unsub = None

    # ── 入向：监听线程调用 ──

    def handle_line(self, msg: dict) -> None:
        method = msg.get("method", "")
        req_id = msg.get("id")

        # watchdog 重启后 sensor 重新 initialize：清 stale 会话映射（D7）
        if method == "initialize":
            dropped = get_registry().drop_by_client(self.name)
            if dropped:
                print(f"♻️ [ACP Bridge] {self.name} 重新 initialize，清理 {dropped} 条 stale 会话")

        # stdio sensor 固定当前活跃会话（硬性行为，sensor 端零决策零配置）：
        # 无条件覆盖——新建/切换会话的逻辑只属于 HTTP 端的编辑器客户端
        if method == "session/new":
            params = msg.setdefault("params", {})
            params["_meta"] = {"purrcat.follow_active": True}

        # upload_file 按 sensor 名落盘（不入网关词汇的传输细节）
        if method == "_purrcat/upload_file":
            params = msg.setdefault("params", {})
            params.setdefault("_meta", {})
            params["_meta"].setdefault("source", self.name)

        resp = handle_rpc(msg)

        if method == "session/new" and "result" in resp:
            self.acp_sid = resp["result"].get("sessionId", "")
            self._ensure_subscribed()

        if req_id is None:
            return  # 通知（如 session/cancel）不回写——与 relay 同契约
        self._write(resp)

        # 持住 prompt：受理凭据已回，真正响应等 turn_end
        if method == "session/prompt" and "result" in resp:
            pid = resp["result"].get("promptId")
            if pid:
                with self._lock:
                    self._pending[pid] = req_id
                    self._pending_order.append(pid)

    # ── 出向：bus 同步回调（Agent 工作线程） ──

    def _on_bus_event(self, envelope: dict) -> None:
        if not self._alive:
            return
        for payload in to_updates(envelope):
            if payload.get("method") == "session/update":
                update = payload["params"]["update"]
                kind = update.get("sessionUpdate", "")
                # tool_detail 关闭时只发正文：过滤思考/工具细节
                if (
                    not self.tool_detail
                    and kind
                    not in ("agent_message_chunk",)
                ):
                    continue
                payload["params"]["sessionId"] = self.acp_sid
                self._write(payload)
                if kind == "agent_message_chunk":
                    self._push_files(update["content"].get("text", ""))
            elif "stopReason" in payload:
                self._finish_prompt(payload["stopReason"])
            # phase 类事件不写 stdin（sensor 不消费）

    def _finish_prompt(self, stop_reason: str) -> None:
        """turn_end 到达：FIFO 回写持住的 prompt 响应"""
        with self._lock:
            if not self._pending_order:
                return
            pid = self._pending_order.pop(0)
            req_id = self._pending.pop(pid, None)
        if req_id is None:
            return
        self._write(
            {"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": stop_reason}}
        )

    def _push_files(self, text: str) -> None:
        """agent 消息提及本地文件路径 → 推 _purrcat/file 通知（base64）"""
        for host_path in extract_file_paths(text):
            try:
                size = os.path.getsize(host_path)
            except OSError:
                continue
            if size > MAX_SENSOR_FILE_BYTES:
                continue
            try:
                with open(host_path, "rb") as f:
                    content_b64 = base64.b64encode(f.read()).decode("ascii")
            except Exception as e:
                print(f"❌ [ACP Bridge] 读文件失败 {host_path}: {e}")
                continue
            mime, _ = mimetypes.guess_type(host_path)
            self._write(
                {
                    "jsonrpc": "2.0",
                    "method": "_purrcat/file",
                    "params": {
                        "name": os.path.basename(host_path),
                        "mime": mime or "application/octet-stream",
                        "size": size,
                        "content_b64": content_b64,
                    },
                }
            )

    # ── 基础设施 ──

    def _ensure_subscribed(self) -> None:
        if self._unsub is not None:
            return
        # follow 模式全订阅：单活跃会话模型下，Agent 事件都来自当前活跃会话
        self._unsub = get_bus().subscribe(None, self._on_bus_event)

    def _write(self, obj: dict) -> None:
        if not self._alive:
            return
        try:
            line = json.dumps(obj, ensure_ascii=False)
            with self._lock:
                self.stdin.write(line + "\n")
                self.stdin.flush()
        except Exception:
            # 进程已死：退订 + 停止响应（监听线程随后也会退出）
            self._alive = False
            self.close()

    def close(self) -> None:
        self._alive = False
        if self._unsub is not None:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
