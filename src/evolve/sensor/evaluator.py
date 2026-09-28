"""
Sensor 协议体检执行器 (evolve/sensor/evaluator.py)

宿主扮演网关（真网关夹具）拉起沙盒 sensor 子进程，把"宿主机真的能看见"的部分全部测掉：

  L0 静态契约：PEP 723 / stdout 重定向 / 无强制退出 / 无硬编码密钥 / env 声明交叉校验
  L1 协议夹具：握手时序 / stdout 纯净 / 空凭证逼出鉴权求助 + sessionId 回填 / 抗污染 /
              错误响应 / 下发不崩 / 永不退出 / 杀后重启可拉起

外部渠道不 mock，故出向投递内容、幂等去重、游标续传属真实链路（合并阶段人审），
报告末尾会显式列出「未覆盖项」，避免把"没测"伪装成"过了"。
"""

import json
import os
import re
import subprocess
import threading
import time

from src.utils.config import AGENT_VM_DIR, get_enriched_env

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

_ENV_PAT = re.compile(
    r"""os\.environ(?:\.get\(|\[)\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""
    r"""|os\.getenv\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""
)
_SECRET_PAT = re.compile(
    r"(?i)\b(token|secret|password|passwd|api_?key|app_?secret|access_?key)\b"
    r"\s*[:=]\s*['\"][A-Za-z0-9_\-\.\+/]{16,}['\"]"
)
_EXIT_PAT = re.compile(r"\b(?:sys\.exit|os\._exit)\s*\(")


def run_sensor_eval_background(workplace_id: str, sensor_name: str):
    """启动后台线程跑协议体检（L0 + L1 免审），完成后系统级通知汇报结果"""

    def _bg_task():
        try:
            report = _run_protocol_eval(workplace_id, sensor_name)
            from src.agent.manager import manager

            manager.agent_force_push(
                f"🔔 【协议体检结果】Sensor '{sensor_name}' (工作区: {workplace_id}) "
                f"的 L0/L1 自动化体检已完成！\n\n{report}",
                type="system",
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            from src.agent.manager import manager

            manager.agent_force_push(
                f"❌ Sensor '{sensor_name}' (工作区: {workplace_id}) 的协议体检崩溃: {e}",
                type="system",
            )

    threading.Thread(
        target=_bg_task, daemon=True, name=f"SensorEval_{workplace_id}"
    ).start()


# --------------------------------------------------------------------------- #
# 通用小工具
# --------------------------------------------------------------------------- #
def _get_next_iteration_dir(workplace_root: str) -> tuple[str, int]:
    """分配新的迭代目录 iteration-N（与 skill/mcp 工厂同一套约定）"""
    max_idx = 0
    if os.path.exists(workplace_root):
        for item in os.listdir(workplace_root):
            match = re.match(r"iteration-(\d+)", item)
            if match:
                max_idx = max(max_idx, int(match.group(1)))
    next_idx = max_idx + 1
    return os.path.join(workplace_root, f"iteration-{next_idx}"), next_idx


def _child_env(declared_keys: list) -> dict:
    """构造 sensor 子进程环境：剥离 venv 痕迹 + 清空声明的凭证以逼出鉴权路径"""
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


# --------------------------------------------------------------------------- #
# L0 静态契约
# --------------------------------------------------------------------------- #
def _static_checks(
    script_text: str, config: dict, config_error: str, sensor_name: str
) -> list:
    cases = []

    def add(case_id, title, passed, detail, level="error"):
        cases.append(
            {
                "id": case_id,
                "layer": "L0",
                "title": title,
                "pass": bool(passed),
                "detail": detail,
                "level": level,
            }
        )

    # 1. PEP 723 内联依赖
    has_pep723 = "# /// script" in script_text and script_text.count("# ///") >= 2
    add(
        "pep723",
        "PEP 723 内联依赖声明",
        has_pep723,
        "已声明内联依赖块" if has_pep723 else "缺少 `# /// script` 内联依赖块，uv run 无法建环境",
    )

    # 2. stdout 重定向（协议通道纯净的前提）
    has_redirect = bool(
        re.search(r"sys\.stdout\s*=\s*sys\.stderr", script_text)
        or re.search(r"_REAL_STDOUT\s*=\s*sys\.stdout", script_text)
    )
    add(
        "stdout_redirect",
        "stdout 重定向到 stderr",
        has_redirect,
        "日志已改道 stderr，协议通道独占 stdout"
        if has_redirect
        else "未见 `sys.stdout = sys.stderr`，print 日志会污染协议通道",
    )

    # 3. 无强制退出
    exit_hit = _EXIT_PAT.search(script_text)
    add(
        "no_force_exit",
        "无强制退出调用",
        not exit_hit,
        "未发现 sys.exit / os._exit"
        if not exit_hit
        else f"发现强制退出调用 `{exit_hit.group(0)}`，违反「严禁退出主进程」铁律",
    )

    # 4. 无硬编码密钥
    secret_hit = _SECRET_PAT.search(script_text)
    add(
        "no_hardcoded_secret",
        "无硬编码密钥",
        not secret_hit,
        "未发现疑似硬编码密钥"
        if not secret_hit
        else f"疑似硬编码密钥: `{secret_hit.group(0)[:60]}...`",
    )

    # 5. sensor_config.json 合法性
    if config_error:
        add("config_valid", "sensor_config.json 可解析", False, config_error)
        declared = []
    else:
        name_ok = config.get("name") == sensor_name
        env_ok = isinstance(config.get("env", {}), dict)
        add(
            "config_valid",
            "sensor_config.json 结构合法",
            name_ok and env_ok,
            f"name={config.get('name')!r}（应为 {sensor_name!r}），env 为对象={env_ok}",
        )
        declared = sorted(config.get("env", {}).keys()) if env_ok else []

    # 6. env 声明交叉校验：代码读了但没声明 —— 合并后用户无从配置
    code_keys = set()
    for match in _ENV_PAT.finditer(script_text):
        code_keys.add(match.group(1) or match.group(2))
    missing = sorted(code_keys - set(declared))
    undeclared_used = [k for k in missing if k not in {"PATH", "HOME", "TMPDIR"}]
    add(
        "env_declared",
        "代码读取的环境变量已全部声明",
        not undeclared_used,
        "代码与 sensor_config.json 的 env 键集一致"
        if not undeclared_used
        else f"代码读取了未声明的环境变量：{', '.join(undeclared_used)}，"
        "合并后用户无法在配置中心填写",
    )
    unused = sorted(set(declared) - code_keys)
    if unused:
        add(
            "env_unused",
            "声明的环境变量确实被使用",
            False,
            f"sensor_config.json 声明了但代码未读取：{', '.join(unused)}",
            level="warn",
        )

    return cases


# --------------------------------------------------------------------------- #
# L1 真网关夹具
# --------------------------------------------------------------------------- #
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
        self._stderr_file = open(self.stderr_path, "w", encoding="utf-8", errors="replace")
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


def _runtime_checks(
    script_path: str, sandbox_root: str, declared: list, iteration_dir: str
) -> tuple[list, dict]:
    cases = []

    def add(case_id, title, passed, detail, level="error"):
        cases.append(
            {
                "id": case_id,
                "layer": "L1",
                "title": title,
                "pass": bool(passed),
                "detail": detail,
                "level": level,
            }
        )

    import shutil

    uv_path = shutil.which("uv")
    if not uv_path:
        add(
            "uv_available",
            "uv 可用",
            False,
            "宿主机 PATH 中找不到 uv，无法拉起 sensor 子进程",
        )
        return cases, {"transcript": []}

    env = _child_env(declared)
    stderr_path = os.path.join(iteration_dir, "sensor_stderr.log")
    fixture = _GatewayFixture(script_path, sandbox_root, env, stderr_path)

    try:
        try:
            fixture.start()
        except Exception as e:
            add("uv_spawn", "uv run 拉起并完成握手", False, f"进程拉起失败: {e}")
            return cases, {"transcript": []}

        # 1. 握手（同时证明 PEP 723 依赖可解析安装）
        got_handshake = fixture.wait_for(fixture.has_handshake, _HANDSHAKE_TIMEOUT)
        add(
            "uv_spawn",
            "uv run 拉起并完成握手",
            got_handshake,
            "进程拉起成功，initialize 与 session/new 均已发出"
            if got_handshake
            else f"超时 {_HANDSHAKE_TIMEOUT:.0f}s 未收到完整握手；"
            "通常是 PEP 723 依赖装不上或启动即崩溃（详见 sensor_stderr.log）",
        )

        handshake_elapsed = None
        if got_handshake:
            first_t, second_t = None, None
            for entry in fixture.transcript:
                if entry["dir"] != "sensor→host":
                    continue
                try:
                    msg = json.loads(entry["raw"])
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == 1 and first_t is None:
                    first_t = entry["t"]
                elif msg.get("id") == 2 and second_t is None:
                    second_t = entry["t"]
            if first_t is not None and second_t is not None:
                handshake_elapsed = round(second_t - first_t, 3)

        add(
            "handshake_order",
            "握手顺序 initialize(1) → session/new(2)",
            got_handshake and fixture.handshake_ok(),
            f"顺序正确，间隔 {handshake_elapsed}s"
            if got_handshake and fixture.handshake_ok()
            else "握手缺失或顺序错乱（必须先是 initialize，再是 session/new）",
        )

        # 2. 空凭证逼出鉴权求助
        got_prompt = fixture.wait_for(lambda: bool(fixture.prompts), _AUTH_PROMPT_TIMEOUT)
        add(
            "auth_prompt",
            "空凭证冷启动发出鉴权求助",
            got_prompt,
            f"已捕获 session/prompt（t={fixture.auth_prompt_at and round(fixture.auth_prompt_at - fixture.started_at, 2)}s）"
            if got_prompt
            else f"超时 {_AUTH_PROMPT_TIMEOUT:.0f}s 未发出任何 session/prompt；"
            "缺凭证时必须主动求助而不是静默哑掉",
        )

        prompt_text = ""
        if got_prompt:
            _, prompts_snapshot, _ = fixture.snapshot()
            prompt_text = _prompt_text(prompts_snapshot[0].get("params", {}))

        # 3. sessionId 回填
        prompts_with_sid = []
        if got_prompt:
            _, prompts_snapshot, _ = fixture.snapshot()
            for prompt in prompts_snapshot:
                prompts_with_sid.append(prompt.get("params", {}).get("sessionId"))
        sid_ok = bool(prompts_with_sid) and all(
            sid == FIXTURE_SESSION_ID for sid in prompts_with_sid
        )
        add(
            "sid_backfill",
            "sessionId 回填正确",
            sid_ok,
            f"session/prompt 携带了网关下发的 sessionId={FIXTURE_SESSION_ID}"
            if sid_ok
            else f"session/prompt 的 sessionId={prompts_with_sid!r}，"
            f"应为网关回填的 {FIXTURE_SESSION_ID!r}（回填错了会导致注入静默失效）",
        )

        # 4. 求助内容质量
        if got_prompt:
            hit_keys = [k for k in declared if k in prompt_text]
            hint_ok = any(
                word in prompt_text for word in ("http", "配置", "获取", "控制台", "官网")
            )
            add(
                "auth_hint",
                "求助文本含凭证名与获取入口",
                bool(hit_keys) and hint_ok,
                f"命中凭证名 {hit_keys}，"
                f"{'含' if hint_ok else '未见'}获取入口提示"
                if hit_keys
                else "求助文本里没有出现已声明的凭证名，用户不知道要填什么",
            )

        # 5. 抗污染：塞垃圾行
        for junk in ("hello", "{", "[]", "不是 JSON 的一行", "x" * 4000):
            fixture.send_raw(junk)
        time.sleep(1.0)
        add(
            "garbage_tolerance",
            "非法输入不崩溃",
            fixture.alive(),
            "注入 5 类垃圾行后进程仍存活" if fixture.alive() else "注入垃圾行后进程已退出",
        )

        # 6. 未知 method 下发
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "_purrcat/unknown_probe",
                "params": {"probe": True},
            }
        )
        # 7. 正常下发（Agent 回复 / 文件 / 轮次结束）
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": FIXTURE_SESSION_ID,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "pong"},
                    },
                },
            }
        )
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "_purrcat/file",
                "params": {
                    "sessionId": FIXTURE_SESSION_ID,
                    "name": "probe.txt",
                    "content_b64": "cHJvYmU=",
                },
            }
        )
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "_purrcat/turn_end",
                "params": {"sessionId": FIXTURE_SESSION_ID},
            }
        )
        time.sleep(1.5)
        add(
            "dispatch_tolerance",
            "未知/正常下发均不崩溃",
            fixture.alive(),
            "未知 method + update/file/turn_end 下发后进程仍存活"
            if fixture.alive()
            else "处理下发消息时进程退出（网络请求可能阻塞在主循环里）",
        )

        # 8. 错误响应容忍：夹具已故意对 session/prompt 回 error
        add(
            "error_response",
            "收到 error 响应不崩溃",
            fixture.alive(),
            "夹具对 session/prompt 回 -32000 错误后进程仍存活"
            if fixture.alive()
            else "收到错误响应后进程退出",
        )

        # 9. stdout 纯净
        _, _, polluted_snapshot = fixture.snapshot()
        add(
            "stdout_purity",
            "stdout 仅承载 JSON-RPC",
            not polluted_snapshot,
            f"抓到 {len(fixture.from_sensor)} 条合法 JSON-RPC"
            if not polluted_snapshot
            else f"发现 {len(polluted_snapshot)} 行非协议输出：{polluted_snapshot[:3]}",
        )

        # 10. 永不退出
        time.sleep(_ALIVE_GRACE)
        add(
            "no_exit",
            "空转不退出",
            fixture.alive(),
            f"静置 {_ALIVE_GRACE:.0f}s 后进程仍存活"
            if fixture.alive()
            else "进程自行退出，违反「严禁退出主进程」铁律",
        )

        # 11. 杀后重启可拉起
        _kill_tree(fixture.proc)
        time.sleep(1.0)
        restart_stderr = os.path.join(iteration_dir, "sensor_stderr_restart.log")
        second = _GatewayFixture(script_path, sandbox_root, env, restart_stderr)
        try:
            second.start()
            restarted = second.wait_for(second.has_handshake, _HANDSHAKE_TIMEOUT)
        except Exception:
            restarted = False
        finally:
            second.close()
        add(
            "restart",
            "杀死后可重新拉起",
            restarted,
            "再次启动并完成握手，未出现双实例冲突"
            if restarted
            else "重启后未能完成握手，热重启/看门狗恢复会失效",
        )

    finally:
        transcript = list(fixture.transcript)
        fixture.close()

    return cases, {"transcript": transcript}


# --------------------------------------------------------------------------- #
# 报告编排
# --------------------------------------------------------------------------- #
def _load_config(config_path: str) -> tuple[dict, str]:
    if not os.path.exists(config_path):
        return {}, "沙盒内未找到 sensor_config.json（合并注册的唯一依据）"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {}, f"sensor_config.json JSON 解析失败: {e}"
    if not isinstance(data, dict):
        return {}, "sensor_config.json 顶层必须是对象"
    return data, ""


_UNCOVERED = [
    "出向投递内容：Agent 回复在外部渠道里长什么样（未 mock 渠道，需真实链路人审）",
    "入向完整链路：外部事件 → session/prompt 的端到端打通",
    "会话跟随语义：prompt 是否真的落进「当前活跃会话」由宿主 stdio 桥强制注入 "
    "follow_active 保证，夹具无桥（直连网关默认 follow=False 会新开会话）故未覆盖",
    "幂等与去重：同一条外部事件重复到达是否只推一次",
    "游标续传：重启后是否不丢、不重复推送",
    "真实网络下的长稳：退避曲线、内存与句柄泄漏",
]


def _render_report(
    sensor_name: str,
    workplace_id: str,
    iteration_idx: int,
    config: dict,
    cases: list,
) -> str:
    errors = [c for c in cases if not c["pass"] and c["level"] == "error"]
    warns = [c for c in cases if not c["pass"] and c["level"] == "warn"]
    passed = len([c for c in cases if c["pass"]])

    lines = [f"# {sensor_name} 协议体检报告 (Iteration {iteration_idx})\n"]
    if errors:
        lines.append(
            f"## 结论：❌ 不通过（{len(errors)} 项硬伤，{len(warns)} 项告警）\n"
        )
    elif warns:
        lines.append(f"## 结论：⚠️ 通过但有告警（{len(warns)} 项）\n")
    else:
        lines.append("## 结论：✅ 全部通过\n")

    lines.append(
        f"- 工作区: `sensor_workplace/{workplace_id}`\n"
        f"- 通过: {passed}/{len(cases)}（错误 {len(errors)} / 告警 {len(warns)}）\n"
        f"- 数据来源: 宿主扮演网关实跑 sensor 子进程，非 Agent 自报\n"
    )

    for layer, title in (("L0", "L0 静态契约"), ("L1", "L1 协议夹具")):
        layer_cases = [c for c in cases if c["layer"] == layer]
        if not layer_cases:
            continue
        lines.append(f"\n## {title}")
        for case in layer_cases:
            if case["pass"]:
                icon = "✅"
            elif case["level"] == "warn":
                icon = "⚠️"
            else:
                icon = "❌"
            lines.append(f"- {icon} **{case['title']}** — {case['detail']}")

    if not any(c["layer"] == "L1" for c in cases):
        lines.append("\n> L1 未执行（uv 不可用或进程拉起失败），协议面完全未覆盖。")

    lines.append("\n## 未覆盖项（属真实链路，随 sensor_merge 人审）")
    for item in _UNCOVERED:
        lines.append(f"- {item}")

    if config.get("source") == "local":
        lines.append(
            "\n> 该 sensor 声明 `source: local`（外部源可本地构造），"
            "可考虑为它补一条本地源闭环用例，把上面前 4 项未覆盖项也自动化。"
        )

    lines.append(
        "\n💡 修复硬伤后请再次 `Request(sensor_test)` 复跑；"
        "L0/L1 全绿再申请 sensor_merge。"
    )
    return "\n".join(lines)


def _run_protocol_eval(workplace_id: str, sensor_name: str) -> str:
    workplace_root = os.path.join(AGENT_VM_DIR, "sensor_workplace", workplace_id)
    script_path = os.path.join(workplace_root, f"{sensor_name}.py")
    config_path = os.path.join(workplace_root, "sensor_config.json")

    if not workplace_root or not os.path.exists(script_path):
        return f"❌ 协议体检失败：未找到沙盒脚本 `{script_path}`"

    try:
        with open(script_path, "r", encoding="utf-8") as f:
            script_text = f.read()
    except OSError as e:
        return f"❌ 协议体检失败：无法读取 `{script_path}`（{e}）"

    config, config_error = _load_config(config_path)
    env_decl = config.get("env", {})
    declared = sorted(env_decl.keys()) if isinstance(env_decl, dict) else []

    iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
    os.makedirs(iteration_dir, exist_ok=True)

    static_cases = _static_checks(
        script_text, config, config_error, sensor_name
    )
    runtime_cases, trace = _runtime_checks(
        script_path, workplace_root, declared, iteration_dir
    )
    cases = static_cases + runtime_cases

    # 取证三件套
    transcript_path = os.path.join(iteration_dir, "handshake.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(trace.get("transcript", []), f, ensure_ascii=False, indent=2)

    passed = len([c for c in cases if c["pass"]])
    err_count = len([c for c in cases if not c["pass"] and c["level"] == "error"])
    benchmark = {
        "sensor": sensor_name,
        "workplace_id": workplace_id,
        "iteration": iteration_idx,
        "summary": {
            "passed": passed,
            "total": len(cases),
            "errors": err_count,
            "warnings": len([c for c in cases if not c["pass"] and c["level"] == "warn"]),
        },
        "cases": cases,
    }
    with open(
        os.path.join(iteration_dir, "benchmark.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(benchmark, f, ensure_ascii=False, indent=2)

    report = _render_report(
        sensor_name, workplace_id, iteration_idx, config, cases
    )
    report += (
        f"\n\n📁 取证文件：`iteration-{iteration_idx}/handshake.json`（全量抓包）、"
        f"`benchmark.json`、`sensor_stderr.log`"
    )
    with open(
        os.path.join(iteration_dir, "protocol_report.md"), "w", encoding="utf-8"
    ) as f:
        f.write(report)

    return report
