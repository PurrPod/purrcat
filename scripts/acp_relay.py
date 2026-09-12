#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
PurrCat ACP 转接（relay）：编辑器 stdio JSON-RPC ⇆ 后端 ACP 网关（HTTP+SSE）

纯搬运工，零词汇翻译（翻译全在网关 src/server/api/acp.py）：
- stdin：读编辑器的 JSON-RPC 行 → POST 转发后端 /acp/rpc，响应原样回写 stdout
  （网关会回填请求 id，id 配对天然成立）
- session/prompt 特殊：网关立即返回受理凭据（accepted/promptId），转接持住请求，
  等 SSE 的 turn_end 事件后按 stopReason 回写真正的 prompt 响应（规范 §4）
- session/cancel 等通知：转发后丢弃 HTTP 响应，不向编辑器回写任何东西
  （通知无响应；网关 HTTP 层是请求-响应模型，收到 {"accepted":true} 只作丢弃）
- SSE → stdout：session/update 通知逐行写出；phase 是自定义事件（非 ACP 词汇），
  绝不写 stdout；turn_end 用于补 prompt 响应

后端发现（优先级）：
1. 环境变量 PURRCAT_ACP_PORT / PURRCAT_ACP_TOKEN
2. ~/.purrcat/settings.json 的 acp_port
3. 默认 http://127.0.0.1:8000；token 固定读 ~/.purrcat/acp_token（后端自动生成）

编辑器接入（Zed settings.json）：
    "agent": {
        "command": "uv",
        "args": ["run", "<repo绝对路径>/scripts/acp_relay.py"]
    }

仅标准库实现；urllib 显式绕过系统代理（ProxyHandler({})），防止 localhost 被
系统代理劫持返回 502（Phase 1 冒烟踩坑记录）。
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# SSE 断流后，挂住的 prompt 最多再等这么久（秒）就回错误响应，防止编辑器 UI 永久卡住
_SSE_FAIL_AFTER = 60
# SSE 连接/读超时（秒）：网关心跳 15s，30s 超时足以判定连接死亡
_SSE_TIMEOUT = 30
# 普通 RPC 超时（秒）
_RPC_TIMEOUT = 15
# session/new 在网关侧排队等 Agent idle（同 chat.py 语义），长轮次期间会阻塞，
# 必须用长超时，否则 Agent 忙时 Zed 开新 chat 会误报连接错误
_RPC_TIMEOUT_SLOW = 3600


# session/load 挂起兜底：SSE 未在此时限内给出 replay_end 就直接放行响应（秒）
_LOAD_FAIL_AFTER = 30


class RelayError(Exception):
    """转发失败（后端不可达等），message 面向用户可读"""


def _log(msg: str) -> None:
    """stderr 日志（规范允许 agent 向 stderr 写日志，客户端可忽略）"""
    print(f"[acp-relay] {msg}", file=sys.stderr, flush=True)


def discover() -> tuple[str, str]:
    """发现后端地址与鉴权 token。token 缺失属配置错误，直接退出给可读提示。"""
    home = Path.home() / ".purrcat"

    port = None
    env_port = os.environ.get("PURRCAT_ACP_PORT", "")
    if env_port.isdigit():
        port = int(env_port)
    if port is None:
        try:
            settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
            v = settings.get("acp_port")
            if isinstance(v, int) and 0 < v < 65536:
                port = v
        except Exception:
            pass
    port = port or 8000

    token = os.environ.get("PURRCAT_ACP_TOKEN", "").strip()
    if not token:
        try:
            token = (home / "acp_token").read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    if not token:
        sys.stderr.write(
            "[acp-relay] 未找到 ACP token（~/.purrcat/acp_token）。"
            "请先启动一次 PurrCat 桌面端以自动生成。\n"
        )
        sys.exit(1)
    return f"http://127.0.0.1:{port}", token


class Relay:
    def __init__(self, base_url: str, token: str):
        self.base = base_url
        self.token = token
        self.lock = threading.Lock()
        self.out = sys.stdout
        # 每个会话一条 SSE 流：sid -> {"gone": bool}（gone=网关侧会话已丢失，终局）
        self.streams: dict[str, dict] = {}
        # 挂住的 prompt：sid -> {"id", "promptId", "fail_at"?}
        self.pending: dict[str, dict] = {}
        # 挂住的 session/load：sid -> {"id", "result", "sent"}（等 replay_end 放行）
        self.load_pending: dict[str, dict] = {}
        # 明确绕过系统代理（httpx trust_env / urllib getproxies 都会劫持 localhost）
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # ==== 输出 ====

    def send(self, obj: dict) -> None:
        """单行紧凑 JSON 写 stdout（规范：消息必须无内嵌换行）"""
        line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        with self.lock:
            self.out.write(line + "\n")
            self.out.flush()

    # ==== HTTP ====

    def rpc(self, msg: dict, timeout: float = _RPC_TIMEOUT) -> dict:
        """转发一条 JSON-RPC 消息到网关 /acp/rpc，返回网关响应 dict"""
        req = urllib.request.Request(
            f"{self.base}/acp/rpc",
            data=json.dumps(msg, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-PurrCat-Token": self.token,
            },
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 网关 HTTP 层错误（401 鉴权失败等）→ 转成 JSON-RPC error 回给编辑器
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {
                    "code": -32000,
                    "message": f"PurrCat gateway HTTP {e.code}",
                },
            }
        except Exception as e:
            raise RelayError(
                f"无法连接 PurrCat 后端（{self.base}）：{e}。请先启动 purrcat 桌面端。"
            )

    # ==== stdin 分发 ====

    def run(self) -> None:
        """主循环：逐行读编辑器 JSON-RPC（阻塞至 stdin 关闭）"""
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _log(f"非 JSON 行已忽略: {line[:80]}")
                continue
            if not isinstance(msg, dict):
                continue
            if "method" in msg:
                if msg.get("id") is not None:
                    self._on_request(msg)
                else:
                    self._on_notification(msg)
            elif msg.get("id") is not None:
                # 编辑器回包（响应网关发起的请求）；v1 网关不发起请求，忽略
                _log(f"丢弃无法路由的客户端响应: {line[:80]}")

    def _on_request(self, msg: dict) -> None:
        method = msg.get("method", "")
        if method == "session/load":
            # 回放事件经 SSE 下发：必须先连流再发请求，否则 replay 的
            # user/agent/tool update 会在流建立前发布而丢失。
            # connected.wait：等订阅真正生效（网关侧队列就绪）才发 RPC
            sid = (msg.get("params") or {}).get("sessionId", "")
            if sid:
                state = self._start_stream(sid)
                if not state["connected"].wait(timeout=_SSE_TIMEOUT):
                    self.send(
                        {
                            "jsonrpc": "2.0",
                            "id": msg["id"],
                            "error": {
                                "code": -32603,
                                "message": "ACP session stream unavailable "
                                "(backend restarted?)",
                            },
                        }
                    )
                    return
        timeout = (
            _RPC_TIMEOUT_SLOW
            if method in ("session/new", "session/load")
            else _RPC_TIMEOUT
        )
        try:
            resp = self.rpc(msg, timeout=timeout)
        except RelayError as e:
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32603, "message": str(e)},
                }
            )
            return
        if "error" in resp:
            self.send(resp)  # 网关错误原样回（id 已由网关回填）
            return
        if method == "session/prompt":
            # 网关只回受理凭据；真正的 stopReason 响应等 SSE turn_end 补
            sid = (msg.get("params") or {}).get("sessionId", "")
            self._hold_prompt(sid, msg["id"], resp.get("result", {}))
            return
        if method == "session/load" and "result" in resp:
            # 规范要求全部回放 update 先于 load 响应：挂住等 SSE replay_end
            sid = (msg.get("params") or {}).get("sessionId", "")
            self._hold_load(sid, msg["id"])
            return
        if method == "session/new":
            sid = resp.get("result", {}).get("sessionId", "")
            if sid:
                self._start_stream(sid)
        self.send(resp)

    def _on_notification(self, msg: dict) -> None:
        """通知（如 session/cancel）：转发后丢弃 HTTP 响应，不回写任何东西"""
        try:
            self.rpc(msg)
        except RelayError as e:
            _log(f"通知转发失败: {e}")

    # ==== prompt 持住 ====

    def _hold_prompt(self, sid: str, req_id, result: dict) -> None:
        state = self.streams.get(sid)
        if state is None or state.get("gone"):
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": "ACP session stream unavailable (backend restarted?)",
                    },
                }
            )
            return
        self.pending[sid] = {"id": req_id, "promptId": result.get("promptId", "")}

    def _fail_pending(self, sid: str, reason: str) -> None:
        pend = self.pending.pop(sid, None)
        if pend is not None:
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": pend["id"],
                    "error": {"code": -32603, "message": reason},
                }
            )

    def _check_pending_deadline(self, sid: str) -> None:
        """SSE 断流期间给挂住的 prompt 计一个 60s 死线，超时回错误防止 UI 卡死"""
        pend = self.pending.get(sid)
        if pend is None:
            return
        if "fail_at" not in pend:
            pend["fail_at"] = time.time() + _SSE_FAIL_AFTER
        elif time.time() > pend["fail_at"]:
            self._fail_pending(
                sid, f"backend SSE stream unreachable for {_SSE_FAIL_AFTER}s"
            )

    # ==== session/load 持住（等 replay_end，保住 update 先于响应的规范顺序） ====

    def _hold_load(self, sid: str, req_id) -> None:
        state = {
            "id": req_id,
            "sent": False,
        }
        self.load_pending[sid] = state
        # 兜底：SSE 异常时也放行响应，防编辑器 UI 永久卡住
        threading.Timer(_LOAD_FAIL_AFTER, self._finish_load, args=(sid, state)).start()

    def _finish_load(self, sid: str, state: dict) -> None:
        if self.load_pending.get(sid) is not state or state.get("sent"):
            return
        state["sent"] = True
        self.load_pending.pop(sid, None)
        self.send({"jsonrpc": "2.0", "id": state["id"], "result": None})

    def _fail_load(self, sid: str, reason: str) -> None:
        state = self.load_pending.pop(sid, None)
        if state is None or state.get("sent"):
            return
        state["sent"] = True
        self.send(
            {
                "jsonrpc": "2.0",
                "id": state["id"],
                "error": {"code": -32603, "message": reason},
            }
        )

    # ==== SSE 消费 ====

    def _start_stream(self, sid: str) -> dict:
        if sid in self.streams:
            return self.streams[sid]
        state = {"gone": False, "connected": threading.Event()}
        self.streams[sid] = state
        threading.Thread(
            target=self._stream_loop, args=(sid, state), daemon=True
        ).start()
        return state

    def _stream_loop(self, sid: str, state: dict) -> None:
        backoff = 1
        while not state.get("gone"):
            try:
                self._consume_stream(sid, state)
                backoff = 1
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    # 网关侧会话映射丢失（后端重启过）：终局，停流并失败挂住的 prompt
                    state["gone"] = True
                    self._fail_pending(
                        sid, f"ACP session lost on backend (HTTP 404): {sid}"
                    )
                    self._fail_load(
                        sid, f"ACP session lost on backend (HTTP 404): {sid}"
                    )
                    return
                _log(f"SSE {sid[:8]}… HTTP {e.code}，稍后重连")
            except Exception as e:
                _log(f"SSE {sid[:8]}… 断开: {e}，重连中")
            self._check_pending_deadline(sid)
            if state.get("gone"):
                return
            time.sleep(backoff)
            backoff = min(backoff * 2, 10)

    def _consume_stream(self, sid: str, state: dict) -> None:
        """阻塞消费一条 SSE 流（连接断开/超时则抛异常回到重连循环）"""
        req = urllib.request.Request(
            f"{self.base}/acp/stream?session={urllib.parse.quote(sid)}",
            headers={
                "X-PurrCat-Token": self.token,
                "Accept": "text/event-stream",
            },
        )
        with self.opener.open(req, timeout=_SSE_TIMEOUT) as resp:
            # 连接成功：清掉挂住 prompt 的失败死线，并广播「流已建立」
            # （session/load 据此确认订阅就绪后才发 RPC，保回放不丢）
            state["connected"].set()
            pend = self.pending.get(sid)
            if pend is not None:
                pend.pop("fail_at", None)
            event = None
            data_lines: list[str] = []
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith(":"):
                    continue  # keepalive 注释
                if not line:
                    if event is not None and data_lines:
                        self._on_stream_event(sid, event, "\n".join(data_lines))
                    event, data_lines = None, []
                    continue
                if line.startswith("event:"):
                    event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:") :].lstrip())
                # retry: 等其它 SSE 指令行忽略

    def _on_stream_event(self, sid: str, event: str, data: str) -> None:
        try:
            obj = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return
        if event == "update":
            # 网关输出的已是完整 session/update JSON-RPC 通知；回填 sessionId 防漂移
            if isinstance(obj, dict) and obj.get("method") == "session/update":
                params = obj.setdefault("params", {})
                params["sessionId"] = sid
                self.send(obj)
        elif event == "turn_end":
            # 据此回写持住的 session/prompt 响应（stopReason）
            pend = self.pending.pop(sid, None)
            if pend is not None:
                self.send(
                    {
                        "jsonrpc": "2.0",
                        "id": pend["id"],
                        "result": {"stopReason": obj.get("stopReason", "end_turn")},
                    }
                )
        elif event == "replay_end":
            # session/load 回放完毕：放行持住的 load 响应（update 已全部送达）
            state = self.load_pending.get(sid)
            if state is not None:
                self._finish_load(sid, state)
        elif event == "phase":
            pass  # 自定义事件（非 ACP 词汇），不得写 stdout


def main() -> None:
    # Windows 管道默认跟随系统编码（中文系统 GBK）；规范要求 JSON-RPC 必须 UTF-8
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    base, token = discover()
    relay = Relay(base, token)
    _log(f"gateway: {base}")
    try:
        relay.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
