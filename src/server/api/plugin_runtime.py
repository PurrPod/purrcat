"""极简模式（web-minimal）：插件后端子进程运行时。

设计目标：让“自带后端功能”的 UI 插件在不修改任何 /api/* 路由的前提下，
以独立子进程方式被拉起，并为插件自带后端管理依赖：插件只需声明
``server/package.json``（推荐附 lockfile），宿主在首次启动/依赖变更时于插件
目录内执行安装（``--omit=dev --ignore-scripts``），主进程的 Python /
PyInstaller 打包完全不接触插件依赖，因此插件可以自由携带任意第三方包，且做到
“装插件即生效 / 改插件热重启 / 卸插件即退出”。只读的内置插件不执行运行时
安装，依赖需随插件目录分发。

治理模型（与调用方约定）：
  - 这是“插件全信”模型：插件运行在其目录下的独立子进程，拥有本地能力。
    若未来要接第三方不可信插件，应改走白名单/沙箱，而非在本模块加开关。

通信协议（stdio 上的单行 JSON，双向）：
  - 主进程 -> 子进程:  {"id": "<nonce>", "handler": "<name>", "payload": {...}}
  - 子进程 -> 主进程:  {"id": "<nonce>", "ok": true, "result": ...}
                        {"id": "<nonce>", "ok": false, "error": "..."}
  - 子进程主动上报:    {"event": "<name>", "data": ...}   （主进程当前仅观测）
子进程接到请求后必须回一行结果；允许多个请求排队（子进程串行处理）。
"""

import json
import os
import shutil
import subprocess
import threading

from src.utils._fs import read_json, write_json_atomic
from src.utils.config import PURRCAT_DIR
from src.server.api.plugin_runtime_support import (
    NODE as _NODE,
    PluginProcessError,
    deps_fingerprint,
    deps_ready,
    locate_plugin_entry,
    strip_venv_env,
)

# 后端依赖安装状态（按插件 id 记录已安装的 package.json/lockfile 指纹）
_DEPS_STATE_DIR = os.path.join(PURRCAT_DIR, "plugin-deps")
_DEPS_LOCK = threading.Lock()
_NPM_TIMEOUT = 300


class _PluginProcess:
    """单个插件的后端子进程句柄（线程安全）。"""

    def __init__(self, plugin_id: str, cwd: str, entry: str, runner: str):
        self.plugin_id = plugin_id
        self.cwd = cwd
        self.entry = entry
        self.runner = runner
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._pending = {}  # nonce -> {"done": bool, "error": str|None, "result": ...}
        self._seq = 0
        self._proc = None
        self._ready = False
        self._last_error = None

    # ---- 进程生命周期 ----
    def _spawn(self):
        if self.runner == _NODE:
            cmd = [self._find_node(), self.entry]
        else:  # pragma: no cover - 仅未来扩展
            raise PluginProcessError(f"不支持的 runner: {self.runner}")
        self._ready = False
        self._last_error = None
        # 继承父进程环境，但剥离 venv 相关变量，避免 uv/pyenv 干扰子进程解释器定位
        env = strip_venv_env(os.environ)
        self._proc = subprocess.Popen(
            cmd,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        threading.Thread(
            target=self._read_loop, daemon=True, name=f"plugin-io-{self.plugin_id}"
        ).start()
        self._wait_ready()

    @staticmethod
    def _find_node() -> str:
        node = shutil.which("node")
        if not node:
            raise PluginProcessError(
                "未找到 node 解释器，无法启动 npm 插件后端（请安装 Node.js 并确保 node 在 PATH）"
            )
        return node

    def _wait_ready(self, timeout: float = 15.0):
        """等待子进程输出 {'event':'ready'} 行（或进程退出/出错）。"""
        with self._lock:
            if self._cond.wait_for(lambda: self._ready or self._dead(), timeout):
                if not self._ready:
                    raise PluginProcessError(
                        f"插件 {self.plugin_id} 后端未就绪: {self._last_error or '启动超时'}"
                    )

    def _dead(self):
        return self._proc is None or self._proc.poll() is not None

    def _read_loop(self):
        """后台线程：逐行解析子进程 stdout，派发 ready / response / event。"""
        proc = self._proc
        reader = proc.stdout
        for raw in reader:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                # 允许子进程打印非 JSON 日志而不崩溃
                continue
            ev = msg.get("event")
            if ev == "ready":
                with self._lock:
                    self._ready = True
                    self._cond.notify_all()
                continue
            nonce = msg.get("id")
            if nonce is not None:
                with self._lock:
                    item = self._pending.get(nonce)
                    if item is not None:
                        item["done"] = True
                        item["error"] = None if msg.get("ok") else str(msg.get("error"))
                        item["result"] = msg.get("result")
                        self._cond.notify_all()
        # stdin EOF：进程已退出，唤醒所有等待者
        with self._lock:
            self._ready = False
            self._last_error = self._drain_stderr()
            self._cond.notify_all()

    def _drain_stderr(self) -> str:
        try:
            return (
                self._proc.stderr.read() if self._proc and self._proc.stderr else ""
            ) or ""
        except Exception:
            return ""

    def stop(self):
        with self._lock:
            proc = self._proc
            self._proc = None
            self._ready = False
            # 唤醒等待者，避免 stuck
            for it in self._pending.values():
                if not it["done"]:
                    it["done"] = True
                    it["error"] = "插件后端已停止"
            self._cond.notify_all()
        if proc:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
            except Exception:
                pass

    # ---- RPC ----
    def rpc(self, handler: str, payload: dict, timeout: float = 30.0):
        with self._lock:
            if self._dead() or not self._ready:
                raise PluginProcessError(f"插件 {self.plugin_id} 后端未运行")
            self._seq += 1
            nonce = f"r{self._seq}"
            req = {"id": nonce, "handler": handler, "payload": payload or {}}
            item = {"done": False, "error": None, "result": None}
            self._pending[nonce] = item
            self._proc.stdin.write(json.dumps(req) + "\n")
            self._proc.stdin.flush()
            if not self._cond.wait_for(lambda: item["done"], timeout):
                raise PluginProcessError(f"插件 {self.plugin_id} 调用 {handler} 超时")
            self._pending.pop(nonce, None)
            if item["error"]:
                raise PluginProcessError(f"{handler}: {item['error']}")
            return item["result"]


# 全局进程表（进程级单例，串行启动/停止）
_PROC_LOCK = threading.Lock()
_PROCESSES: dict[str, _PluginProcess] = {}


def _deps_state_path(plugin_id: str) -> str:
    return os.path.join(_DEPS_STATE_DIR, f"{plugin_id}.json")


def _read_deps_state(plugin_id: str) -> dict:
    data = read_json(_deps_state_path(plugin_id))
    return data if isinstance(data, dict) else {}


def _write_deps_state(plugin_id: str, fingerprint: str):
    path = _deps_state_path(plugin_id)
    write_json_atomic(path, {"fingerprint": fingerprint}, indent=None)


def _run_npm(args: list, cwd: str) -> subprocess.CompletedProcess:
    """执行 npm；Windows 下 npm 是 .cmd，必须经 cmd.exe 运行。"""
    npm = shutil.which("npm")
    if not npm:
        raise PluginProcessError("未找到 npm：插件后端依赖安装需要 Node.js 环境")
    kwargs = dict(
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_NPM_TIMEOUT,
    )
    try:
        if os.name == "nt":
            return subprocess.run(
                subprocess.list2cmdline([npm] + args), shell=True, **kwargs
            )
        return subprocess.run([npm] + args, **kwargs)
    except subprocess.TimeoutExpired:
        raise PluginProcessError(f"插件后端依赖安装超时（>{_NPM_TIMEOUT}s）")
    except Exception as e:
        raise PluginProcessError(f"插件后端依赖安装失败：{e}")


def _ensure_dependencies(plugin_id: str, plugin_dir: str, allow_install: bool):
    """确保插件后端依赖可用；已随插件分发 node_modules 时直接复用。"""
    server_dir = os.path.join(plugin_dir, "server")
    if not os.path.isfile(os.path.join(server_dir, "package.json")):
        return
    fingerprint = deps_fingerprint(server_dir)
    node_modules = os.path.join(server_dir, "node_modules")

    state = _read_deps_state(plugin_id)
    if deps_ready(server_dir, fingerprint, state):
        return
    # 插件自带 node_modules（作者已打包依赖）时信任现成结果，不联网重装。
    if os.path.isdir(node_modules) and not state:
        _write_deps_state(plugin_id, fingerprint)
        return
    if not allow_install:
        return

    with _DEPS_LOCK:
        # 等锁期间状态可能已被其它调用更新，重新读取指纹与状态再判断。
        fingerprint = deps_fingerprint(server_dir)
        state = _read_deps_state(plugin_id)
        if deps_ready(server_dir, fingerprint, state):
            return
        has_lock = any(
            os.path.isfile(os.path.join(server_dir, name))
            for name in ("package-lock.json", "npm-shrinkwrap.json")
        )
        args = ["ci" if has_lock else "install"]
        args += ["--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"]
        result = _run_npm(args, server_dir)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip()[-1200:]
            raise PluginProcessError(
                f"插件 {plugin_id} 后端依赖安装失败：{tail or 'npm 返回非零退出码'}"
            )
        # 安装会生成/更新 lockfile，必须记录安装后的指纹，否则下次会重复安装。
        _write_deps_state(plugin_id, deps_fingerprint(server_dir))


def _get_or_start(
    plugin_id: str, plugin_dir: str, allow_install: bool = True
) -> _PluginProcess:
    """获取已运行的进程；未运行则拉起新进程。跨线程安全。"""
    if not os.path.isdir(plugin_dir):
        raise PluginProcessError(f"插件 {plugin_id} 目录不存在")
    _ensure_dependencies(plugin_id, plugin_dir, allow_install)
    with _PROC_LOCK:
        proc = _PROCESSES.get(plugin_id)
        if (
            proc is not None
            and proc._proc
            and proc._proc.poll() is None
            and proc._ready
        ):
            return proc
        # 旧进程（无论崩溃与否）先回收
        if proc is not None:
            proc.stop()
            _PROCESSES.pop(plugin_id, None)
        if not os.path.isdir(plugin_dir):
            raise PluginProcessError(f"插件 {plugin_id} 目录不存在")
        cwd, entry, runner = locate_plugin_entry(plugin_dir)
        proc = _PluginProcess(plugin_id, cwd, entry, runner)
        proc._spawn()
        _PROCESSES[plugin_id] = proc
        return proc


def rpc_plugin(
    plugin_id: str,
    plugin_dir: str,
    handler: str,
    payload: dict,
    timeout: float = 30.0,
    allow_install: bool = True,
):
    """对外 RPC 入口：确保进程在跑并调用其 handler。"""
    proc = _get_or_start(plugin_id, plugin_dir, allow_install=allow_install)
    return proc.rpc(handler, payload, timeout)


def restart(plugin_id: str):
    with _PROC_LOCK:
        proc = _PROCESSES.pop(plugin_id, None)
    if proc:
        proc.stop()
    return True


def start(plugin_id: str, plugin_dir: str, allow_install: bool = True):
    """主动拉起插件后端子进程（不依赖首次 RPC）。"""
    proc = _get_or_start(plugin_id, plugin_dir, allow_install=allow_install)
    return {"running": True, "pid": proc._proc.pid if proc._proc else None}


def stop(plugin_id: str):
    return restart(plugin_id)


def stop_all():
    with _PROC_LOCK:
        procs = list(_PROCESSES.values())
        _PROCESSES.clear()
    for p in procs:
        p.stop()


def is_running(plugin_id: str) -> bool:
    proc = _PROCESSES.get(plugin_id)
    return proc is not None and proc._proc and proc._proc.poll() is None
