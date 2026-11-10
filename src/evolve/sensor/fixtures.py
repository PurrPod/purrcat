"""Sensor 协议体检的网关夹具与子进程工具（SPEC-020）。

夹具扮演网关，负责 JSON-RPC 收发与抓包；本模块只依赖标准库。
"""

import json
import os
import subprocess
import threading
import time

from src.utils.config import get_enriched_env

# 夹具回填给 sensor 的假会话号：sensor 后续所有 session/prompt 都必须带上它
FIXTURE_SESSION_ID = "SID_TEST"

_HANDSHAKE_TIMEOUT = 120.0  # 首次 uv 建环境可能较慢
_AUTH_PROMPT_TIMEOUT = 90.0
_ALIVE_GRACE = 5.0

# 子进程不得继承父进程 venv 痕迹，否则 uv 定位不到标准库
_VENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)


def _child_env(declared_keys: list) -> dict:
    """构造 sensor 子进程环境：剥离 venv 痕迹 + 清空声明的凭证以逼出缺凭证的失败上报路径"""
    env = dict(get_enriched_env())
    for key in _VENV_KEYS:
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    for key in declared_keys:
        env[key] = ""
    return env


def _kill_tree(proc: subprocess.Popen):
    """连根拔起（uv run 会派生真正的 python 子进程）"""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _prompt_text(params: dict) -> str:
    """从 session/prompt 的 params 里拼出纯文本"""
    chunks = params.get("prompt") or []
    if isinstance(chunks, str):
        return chunks
    texts = []
    for block in chunks:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(str(block.get("text", "")))
    return "\n".join(texts)


class _GatewayFixture:
    """托管 sensor 子进程，扮演网关做 JSON-RPC 收发与抓包"""

    def __init__(self, script_path: str, cwd: str, env: dict, stderr_path: str):
        self.script_path = script_path
        self.cwd = cwd
        self.env = env
        self.stderr_path = stderr_path
        self.proc = None
        self.transcript = []  # 全量抓包，用于事后取证
        self.from_sensor = []  # sensor → host
        self.to_sensor = []  # host → sensor
        self.polluted = []  # 非 JSON-RPC 的 stdout 行
        self.requests = []  # sensor 发来的请求
        self.prompts = []  # 抓到的 session/prompt
        self.started_at = 0.0
        self.handshake_at = None
        self.auth_prompt_at = None
        self._stderr_file = None
        self._lock = threading.Lock()

    # -- 生命周期 ---------------------------------------------------------- #
    def start(self):
        self._stderr_file = open(
            self.stderr_path, "w", encoding="utf-8", errors="replace"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            ["uv", "run", self.script_path],
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
        )
        self.started_at = time.time()
        threading.Thread(
            target=self._pump, daemon=True, name="SensorFixturePump"
        ).start()

    def close(self):
        _kill_tree(self.proc)
        if self._stderr_file:
            try:
                self._stderr_file.close()
            except Exception:
                pass
            self._stderr_file = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # -- 收发 -------------------------------------------------------------- #
    def _elapsed(self) -> float:
        return round(time.time() - self.started_at, 3)

    def _record(self, direction: str, raw: str):
        with self._lock:
            self.transcript.append(
                {"t": self._elapsed(), "dir": direction, "raw": raw.rstrip("\n")}
            )

    def send(self, obj: dict):
        if not self.alive():
            return
        line = json.dumps(obj, ensure_ascii=False)
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except Exception:
            return
        with self._lock:
            self.to_sensor.append(obj)
        self._record("host→sensor", line)

    def send_raw(self, raw: str):
        """往 sensor stdin 塞一行原始文本（不做 JSON 序列化），用于抗污染用例"""
        if not self.alive():
            return
        try:
            self.proc.stdin.write(raw + "\n")
            self.proc.stdin.flush()
        except Exception:
            return
        self._record("host→sensor", raw)

    def snapshot(self) -> tuple:
        """线程安全地取一份请求/纯净度快照"""
        with self._lock:
            return list(self.requests), list(self.prompts), list(self.polluted)

    def _reply(self, req: dict):
        """按网关语义回包；session/prompt 故意回 error 以验证错误容忍"""
        req_id = req.get("id")
        if req_id is None:
            return
        method = req.get("method", "")
        if req_id == 2 and method == "session/new":
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"sessionId": FIXTURE_SESSION_ID},
                }
            )
        elif method == "session/prompt":
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": "fixture: injected error"},
                }
            )
        elif method in ("initialize", "session/cancel"):
            self.send({"jsonrpc": "2.0", "id": req_id, "result": {}})
        else:
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "fixture: method not found"},
                }
            )

    def _pump(self):
        try:
            for line in self.proc.stdout:
                self._record("sensor→host", line)
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    msg = json.loads(stripped)
                except json.JSONDecodeError:
                    with self._lock:
                        self.polluted.append(stripped)
                    continue
                if not isinstance(msg, dict):
                    with self._lock:
                        self.polluted.append(stripped)
                    continue
                with self._lock:
                    self.from_sensor.append(msg)
                if "method" in msg:
                    if msg.get("method") == "session/prompt":
                        with self._lock:
                            self.prompts.append(msg)
                        if self.auth_prompt_at is None:
                            self.auth_prompt_at = time.time()
                    self.requests.append(msg)
                    self._reply(msg)
                elif "id" not in msg:
                    # 无 method 也无 id 的合法 JSON —— 仍然是协议噪声
                    with self._lock:
                        self.polluted.append(stripped)
        except Exception:
            pass

    def wait_for(self, pred, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if pred():
                    return True
            if not self.alive():
                return False
            time.sleep(0.2)
        with self._lock:
            return bool(pred())

    def has_handshake(self) -> bool:
        ids = [r.get("id") for r in self.requests]
        return 1 in ids and 2 in ids

    def handshake_ok(self) -> bool:
        """initialize(id=1) 必须早于 session/new(id=2)，且顺序里没有别的请求插队"""
        ordered = []
        for req in self.requests:
            req_id = req.get("id")
            if req_id in (1, 2) and req_id not in ordered:
                ordered.append(req_id)
        return ordered[:2] == [1, 2]

    def injected_ids(self) -> list:
        return [m.get("id") for m in self.from_sensor if "method" not in m]
