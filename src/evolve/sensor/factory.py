"""
Sensor 进化工厂核心逻辑 (evolve/sensor/factory.py)

单文件沙盒模式：Sensor 本体是单个 <name>.py（PEP 723 内联依赖），
沙盒内配套 sensor_config.json 作为合并注册的唯一依据。
"""

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime

from src.utils.config import (
    SENSOR_EXTENSION_DIR,
    SENSOR_CONFIG_PATH,
    AGENT_VM_DIR,
)

from .guide_generator import generate_sensor_guide


def _skeleton(sensor_name: str) -> str:
    """全新 sensor 的可运行骨架（ACP 方言）：握手 → 鉴权求助 → 事件线程 → update 消费循环"""
    return f'''# /// script
# requires-python = ">=3.10"
# dependencies = [
#     # 在此声明依赖，如 "lark-oapi"
# ]
# ///

import sys
import json
import os
import threading
import time

# 🌟 铁律：stdout 是协议通道，print 日志必须全部转到 stderr
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

SENSOR_NAME = "{sensor_name}"
_SESSION_NEW_ID = 2

_REQ_ID = 2  # 1/2 留给握手
_REQ_LOCK = threading.Lock()
_PENDING = {{}}  # rid -> {{"event", "result"}}（仅 track=True 的请求可等响应）
_SID = ""
_SID_READY = threading.Event()


def send_request(method: str, params: dict, track: bool = False, rid=None) -> int:
    global _REQ_ID
    with _REQ_LOCK:
        if rid is None:
            _REQ_ID += 1
            rid = _REQ_ID
        if track:
            _PENDING[rid] = {{"event": threading.Event(), "result": None}}
    _REAL_STDOUT.write(
        json.dumps(
            {{"jsonrpc": "2.0", "id": rid, "method": method, "params": params}},
            ensure_ascii=False,
        )
        + "\\n"
    )
    _REAL_STDOUT.flush()
    return rid


def wait_response(rid: int, timeout: float = 30.0):
    """等你发出的某个请求的响应（仅 track=True 的请求可等）"""
    h = _PENDING.get(rid)
    if not h:
        return None
    h["event"].wait(timeout)
    with _REQ_LOCK:
        return _PENDING.pop(rid, {{}}).get("result")


def acp_connect() -> None:
    """握手：initialize + session/new（宿主 stdio 桥会强制改写为 follow_active，
    使后续 prompt 直达当前活跃会话；此保证来自桥，不是网关默认值）"""
    send_request("initialize", {{"clientInfo": {{"name": SENSOR_NAME}}}}, rid=1)
    send_request(
        "session/new", {{"clientInfo": {{"name": SENSOR_NAME}}}}, rid=_SESSION_NEW_ID
    )


def prompt_agent(text: str) -> None:
    """外部事件（用户消息/提醒/鉴权求助）注入当前活跃会话。

    🌟 必须先等 session/new 的响应拿到 sessionId 再发——带着空 sessionId 发出去的
    prompt 会被网关静默丢弃，表现为"求助消息没人收到"。
    """
    _SID_READY.wait(timeout=30)
    if not _SID:
        print(f"❌ [{{SENSOR_NAME}}] 未拿到 sessionId，本次注入被跳过")
        return
    send_request(
        "session/prompt",
        {{"sessionId": _SID, "prompt": [{{"type": "text", "text": text}}]}},
    )


def handle_notification(msg: dict) -> None:
    """处理网关下发：session/update（Agent 回复）与 _purrcat/file（文件）"""
    method = msg.get("method", "")
    params = msg.get("params", {{}})

    if method == "session/update":
        update = params.get("update", {{}})
        kind = update.get("sessionUpdate", "")
        if kind in ("agent_message", "agent_message_chunk"):
            text = update.get("content", {{}}).get("text", "")
            print(f"💬 [{{SENSOR_NAME}}] 收到 Agent 回复: {{text}}")
            # TODO: 把 text 转发到外部渠道（注意在后台线程执行网络请求）
    elif method == "_purrcat/file":
        import base64

        name = params.get("name", "file")
        data = base64.b64decode(params.get("content_b64", ""))
        print(f"📎 [{{SENSOR_NAME}}] 收到网关文件: {{name}} ({{len(data)}} bytes)")
        # TODO: 解码后发送到外部渠道（注意在后台线程执行网络请求）


def check_auth() -> bool:
    """首次启动鉴权检查：缺凭证必须发文字消息向 Agent 求助，严禁静默退出"""
    # TODO: 按实际情况替换凭证名
    token = os.environ.get("MY_TOKEN", "")
    if not token:
        prompt_agent(
            "[{sensor_name} 求助] 首次启动需要鉴权凭证 MY_TOKEN（当前为空）。"
            "请前往 https://example.com/console 依次进入「开发者设置 → 凭证管理」"
            "复制 Token（按实际情况替换为真实控制台地址与步骤），"
            "回填到前端配置中心 → Sensor 设置 → {sensor_name} 后保存启用，"
            "我会在热重启后自动连接并保持待命。"
        )
        return False
    return True


def start_event_listener():
    """后台线程：连接外部服务，把事件 prompt 给 Agent。此处为占位示例。"""

    def _worker():
        while True:
            try:
                # TODO: 替换为真实外部服务连接/监听逻辑
                time.sleep(3600)
            except Exception as e:
                print(f"❌ [{{SENSOR_NAME}}] 事件监听崩溃，5秒后重试: {{e}}")
                time.sleep(5)

    threading.Thread(target=_worker, daemon=True).start()


def bootstrap() -> None:
    """等握手完成（拿到 sessionId）后再鉴权与起监听，避免注入被静默丢弃"""
    if not _SID_READY.wait(timeout=30):
        print(f"⚠️ [{{SENSOR_NAME}}] 等待会话绑定超时，保持存活待命")
    if not check_auth():
        # 凭证未就绪：仍保持进程存活，热重启读到新 env 后自动恢复
        pass
    start_event_listener()


def stdin_loop() -> None:
    """主线程：消费网关下发（session/new 响应用于回填 sessionId）"""
    global _SID
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue  # 合法 JSON 但不是对象（如 []、123），一律忽略，绝不崩主循环
        if "method" in msg:
            try:
                handle_notification(msg)
            except Exception as e:
                print(f"❌ [{{SENSOR_NAME}}] 处理下发消息异常: {{e}}")
            continue
        if msg.get("id") == _SESSION_NEW_ID and "result" in msg:
            _SID = (msg.get("result") or {{}}).get("sessionId", "")
            _SID_READY.set()
            continue
        rid = msg.get("id")
        with _REQ_LOCK:
            h = _PENDING.get(rid)
        if h is not None:
            h["result"] = msg.get("result") if "result" in msg else msg.get("error")
            h["event"].set()


acp_connect()
threading.Thread(target=bootstrap, daemon=True).start()
stdin_loop()
'''


def _config_template(sensor_name: str) -> str:
    return json.dumps(
        {
            "name": sensor_name,
            "env": {"MY_TOKEN": ""},
            "tool_detail": False,
            "source": "remote",
        },
        indent=2,
        ensure_ascii=False,
    )


def _gateway_probe() -> str:
    """沙盒自测夹具：宿主同款真网关的精简版，供 Agent 免提交快速自检协议面"""
    return '''#!/usr/bin/env python3
"""Sensor 沙盒自测夹具（真网关精简版）

用法（在沙盒根目录执行）:
    uv run evals/gateway_probe.py

它扮演网关拉起同级目录里的 sensor，验证：握手顺序 / 空凭证求助 / sessionId 回填 /
stdout 纯净 / 空转存活。宿主侧的正式体检（含 L0 静态契约）由 Request(sensor_test) 触发。
"""

import json
import os
import subprocess
import sys
import threading
import time

SID = "SID_SELFTEST"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STDERR_LOG = os.path.join(ROOT, "evals", "probe_stderr.log")


def find_sensor():
    """优先用 sensor_config.json 的 name 定位本体，否则退化为根目录第一个 .py"""
    cfg_path = os.path.join(ROOT, "sensor_config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                name = json.load(f).get("name")
            if name:
                path = os.path.join(ROOT, "%s.py" % name)
                if os.path.isfile(path):
                    return name, path
        except Exception:
            pass
    for item in sorted(os.listdir(ROOT)):
        if item.endswith(".py") and not item.startswith("_"):
            path = os.path.join(ROOT, item)
            if os.path.isfile(path):
                return item, path
    return None, None


def declared_env(sensor_name):
    cfg_path = os.path.join(ROOT, "sensor_config.json")
    if not os.path.exists(cfg_path):
        return []
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            env = json.load(f).get("env", {})
        return sorted(env.keys()) if isinstance(env, dict) else []
    except Exception:
        return []


def main():
    sensor_name, script = find_sensor()
    if not script:
        print("\\u274c 未在沙盒根目录找到 sensor 脚本")
        return 1

    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(key, None)
    for key in declared_env(sensor_name):
        env[key] = ""

    stderr_f = open(STDERR_LOG, "w", encoding="utf-8", errors="replace")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        ["uv", "run", script],
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_f,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=flags,
    )

    requests, prompts, polluted = [], [], []
    started = time.time()

    def pump():
        for line in proc.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                msg = json.loads(stripped)
            except json.JSONDecodeError:
                polluted.append(stripped)
                continue
            if not isinstance(msg, dict):
                polluted.append(stripped)
                continue
            if "method" in msg:
                if msg.get("method") == "session/prompt":
                    prompts.append(msg)
                req_id = msg.get("id")
                if req_id == 2 and msg.get("method") == "session/new":
                    reply = {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": SID}}
                elif req_id is not None:
                    reply = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32000, "message": "probe"},
                    }
                else:
                    continue
                try:
                    proc.stdin.write(json.dumps(reply) + "\\n")
                    proc.stdin.flush()
                except Exception:
                    pass
                requests.append(msg)
            elif "id" in msg:
                requests.append(msg)

    threading.Thread(target=pump, daemon=True).start()

    def wait(pred, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline and proc.poll() is None:
            if pred():
                return True
            time.sleep(0.2)
        return pred()

    got_handshake = wait(
        lambda: any(r.get("id") == 1 for r in requests)
        and any(r.get("id") == 2 for r in requests),
        120,
    )
    got_prompt = wait(lambda: bool(prompts), 90)
    time.sleep(3)
    alive = proc.poll() is None

    order = [r.get("id") for r in requests if r.get("id") in (1, 2)]
    seen, ordered = set(), []
    for i in order:
        if i not in seen:
            seen.add(i)
            ordered.append(i)

    sid = prompts[0].get("params", {}).get("sessionId") if prompts else None
    text = ""
    if prompts:
        for block in prompts[0].get("params", {}).get("prompt", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

    checks = [
        ("uv 拉起并完成握手", got_handshake, "检查 PEP 723 依赖与启动异常"),
        ("握手顺序 1 \\u2192 2", ordered[:2] == [1, 2], "必须先 initialize 再 session/new"),
        ("空凭证发出求助", got_prompt, "缺凭证必须 session/prompt 求助，不能静默哑掉"),
        ("sessionId 回填", sid == SID, "应为网关回填的 %s，当前 %r" % (SID, sid)),
        ("stdout 纯净", not polluted, "非协议输出: %r" % (polluted[:2],)),
        ("空转不退出", alive, "进程自行退出（详见 evals/probe_stderr.log）"),
    ]

    print("=" * 56)
    print("Sensor 自测夹具（真网关精简版）: %s" % sensor_name)
    print("=" * 56)
    failed = 0
    for title, ok, hint in checks:
        if ok:
            print("  \\u2705 %s" % title)
        else:
            failed += 1
            print("  \\u274c %s \\u2014 %s" % (title, hint))

    if text:
        print("\\n\\u2139\\ufe0f 抓到的求助文本:\\n%s" % text[:400])

    if proc.poll() is None:
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
    stderr_f.close()

    print(
        "\\n%s  用时 %.1fs，stderr 日志: evals/probe_stderr.log"
        % ("\\u2705 自测通过" if failed == 0 else "\\u274c %d 项未通过" % failed,
           time.time() - started)
    )
    print("提示：宿主正式体验证请用 Request(sensor_test)，它还会跑 L0 静态契约。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
'''


def _write_goal_and_guide(workplace_root: str, sensor_name: str, goal: str):
    if goal:
        with open(
            os.path.join(workplace_root, "GOAL.md"), "w", encoding="utf-8", newline="\n"
        ) as f:
            f.write(f"# 🎯 Build Goal\n\n{goal}\n")
    with open(
        os.path.join(workplace_root, "GUIDE.md"), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write(generate_sensor_guide(sensor_name, goal))


def sensor_factory_init(
    sensor_name: str, is_upgrade: bool, goal: str = ""
) -> tuple[str, str]:
    """初始化 Sensor 进化沙盒，返回 (系统提示, workplace_id)"""
    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = os.path.join(AGENT_VM_DIR, "sensor_workplace", short_uuid)
    script_path = os.path.join(workplace_root, f"{sensor_name}.py")

    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    os.makedirs(workplace_root, exist_ok=True)

    if is_upgrade:
        source = os.path.join(SENSOR_EXTENSION_DIR, f"{sensor_name}.py")
        if not os.path.exists(source):
            return f"❌ 无法执行升级：正式目录中未找到 '{sensor_name}.py'。", ""
        shutil.copy2(source, script_path)
        # 沿用现有注册配置（env 已填的值不丢），缺则补模板
        from src.utils.config import get_sensor_config

        cfg = (get_sensor_config() or {}).get(sensor_name, {})
        config = {
            "name": sensor_name,
            "env": cfg.get("env") or {"MY_TOKEN": ""},
            "tool_detail": cfg.get("tool_detail", False),
            "source": cfg.get("source", "remote"),
        }
        with open(
            os.path.join(workplace_root, "sensor_config.json"),
            "w",
            encoding="utf-8",
            newline="\n",
        ) as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        action_msg = f"已将现有的 '{sensor_name}.py' 拷贝至进化沙盒进行升级"
    else:
        with open(script_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(_skeleton(sensor_name))
        with open(
            os.path.join(workplace_root, "sensor_config.json"),
            "w",
            encoding="utf-8",
            newline="\n",
        ) as f:
            f.write(_config_template(sensor_name))
        action_msg = f"已为你搭建了全新的 '{sensor_name}' 可运行骨架（含鉴权求助示例）"

    evals_dir = os.path.join(workplace_root, "evals")
    os.makedirs(evals_dir, exist_ok=True)
    with open(
        os.path.join(evals_dir, "gateway_probe.py"), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write(_gateway_probe())

    _write_goal_and_guide(workplace_root, sensor_name, goal)

    sandbox_root = f"/agent_vm/sensor_workplace/{short_uuid}"
    return (
        f"【Sensor 工厂分配成功】工作区路径：{sandbox_root}（workplace_id: {short_uuid}）。\n"
        f"{action_msg}。\n"
        f"💡 提示：系统已在沙盒根目录为你生成了官方说明文档 GUIDE.md"
        f"（覆盖 stdio 协议/鉴权求助/文件收发/提交全流程），动手前请先通读！\n"
        f"🧪 自测夹具：`evals/gateway_probe.py`（宿主同款真网关精简版），"
        f"在沙盒根目录执行 `uv run evals/gateway_probe.py` 即可验证握手/鉴权求助/"
        f"sessionId 回填/stdout 纯净/存活，通过后再提交 Request(sensor_test) 做正式体检。"
    ), short_uuid


def _hot_restart_sensors():
    """合并后在后台线程热重启 Sensor 线程池，让新 sensor 立即生效"""

    def _worker():
        try:
            from src.sensor.manager import get_manager

            manager = get_manager()
            manager.stop_all()
            manager.load_and_start_all()
            print("✅ [Sensor工厂] 合并后热重启完成")
        except Exception as e:
            print(
                f"⚠️ [Sensor工厂] 合并后热重启失败（不影响代码合并，可手动 reload）: {e}"
            )

    threading.Thread(
        target=_worker, daemon=True, name="Sensor-Merge-HotRestart"
    ).start()


def _latest_protocol_verdict(workplace_root: str) -> tuple[bool, str]:
    """读取最近一次协议体检结论，并校验其是否对应当前代码（证据不许过期）"""
    latest_dir, latest_idx = None, 0
    for item in os.listdir(workplace_root) if os.path.exists(workplace_root) else []:
        m = re.match(r"iteration-(\d+)$", item)
        if m and int(m.group(1)) > latest_idx:
            latest_idx, latest_dir = int(m.group(1)), os.path.join(workplace_root, item)
    if not latest_dir:
        return False, "尚无任何协议体检记录"

    bench_path = os.path.join(latest_dir, "benchmark.json")
    if not os.path.exists(bench_path):
        return False, f"iteration-{latest_idx} 内没有 benchmark.json"
    try:
        with open(bench_path, "r", encoding="utf-8") as f:
            bench = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"iteration-{latest_idx}/benchmark.json 无法解析: {e}"

    summary = bench.get("summary", {})
    errors = summary.get("errors", 0)
    if errors:
        return False, f"iteration-{latest_idx} 仍有 {errors} 项硬伤未修复"

    script_path = os.path.join(workplace_root, f"{bench.get('sensor', '')}.py")
    if os.path.exists(script_path):
        newer = [
            item
            for item in os.listdir(workplace_root)
            if item.endswith(".py")
            and os.path.getmtime(os.path.join(workplace_root, item))
            > os.path.getmtime(bench_path)
        ]
        if newer:
            return (
                False,
                f"体检后又改动过 {', '.join(newer)}，证据已过期，需重跑 sensor_test",
            )

    return (
        True,
        f"iteration-{latest_idx} 协议体检通过（{summary.get('passed', 0)}/{summary.get('total', 0)}）",
    )


def sensor_request_handle(
    workplace_root: str, sensor_name: str, is_approved: bool
) -> str:
    """处理 Sensor 合并请求：拷贝正式目录 + 写 activate_sensor.json + 热重启"""
    if not is_approved:
        return f"人类拒绝了 {sensor_name} 的合并请求，已保留当前工作区供调整。"

    source_path = os.path.join(workplace_root, f"{sensor_name}.py")
    if not os.path.exists(source_path):
        return f"❌ 合并失败：沙盒中未找到 '{sensor_name}.py'，请补齐后再申请合并。"

    # 0. 协议体检把关：L0/L1 必须全绿，且证据对应当前代码
    verdict_ok, verdict_text = _latest_protocol_verdict(workplace_root)
    if not verdict_ok:
        return (
            f"❌ 合并被阻止：{verdict_text}。\n"
            f"请先执行 `Request(sensor_test, target='{os.path.basename(workplace_root)}/{sensor_name}')` "
            f"跑完协议体检并修复全部硬伤后再申请合并。"
        )

    # 1. 强校验：读取 Agent 维护的 sensor_config.json（注册唯一依据）
    config_path = os.path.join(workplace_root, "sensor_config.json")
    if not os.path.exists(config_path):
        return (
            "❌ 合并失败：沙盒中丢失了必需的 `sensor_config.json`，"
            "请按 GUIDE.md 第 6 节补齐后再申请合并。"
        )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            sandbox_config = json.load(f)
    except json.JSONDecodeError:
        return "❌ 合并失败：`sensor_config.json` JSON 格式损坏，请修复后再申请合并。"

    env_data = sandbox_config.get("env", {})
    if not isinstance(env_data, dict):
        env_data = {}

    # 2. 拷贝 Sensor 本体至正式目录
    os.makedirs(SENSOR_EXTENSION_DIR, exist_ok=True)
    target_path = os.path.join(SENSOR_EXTENSION_DIR, f"{sensor_name}.py")
    is_upgrade = os.path.exists(target_path)
    shutil.copy2(source_path, target_path)

    # 3. Git 版本接管（首次自动 init）
    if not os.path.exists(os.path.join(SENSOR_EXTENSION_DIR, ".git")):
        subprocess.run(["git", "init"], cwd=SENSOR_EXTENSION_DIR)
        with open(
            os.path.join(SENSOR_EXTENSION_DIR, ".gitignore"), "w", encoding="utf-8"
        ) as f:
            f.write("__pycache__/\n*.pyc\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=SENSOR_EXTENSION_DIR)
    subprocess.run(["git", "add", f"{sensor_name}.py"], cwd=SENSOR_EXTENSION_DIR)
    commit_msg = (
        f"{'upgrade' if is_upgrade else 'add'} sensor {sensor_name} "
        f"{datetime.now().strftime('%Y-%m-%d')}"
    )
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=SENSOR_EXTENSION_DIR)

    # 4. 注入 activate_sensor.json（enabled=true，env 空值留待用户填写）
    sensor_config = {}
    if os.path.exists(SENSOR_CONFIG_PATH):
        try:
            with open(SENSOR_CONFIG_PATH, "r", encoding="utf-8") as f:
                sensor_config = json.load(f)
        except Exception:
            pass
    sensor_config[sensor_name] = {
        "enabled": True,
        "env": env_data,
        "tool_detail": bool(sandbox_config.get("tool_detail", False)),
        "source": sandbox_config.get("source", "remote"),
    }
    os.makedirs(os.path.dirname(SENSOR_CONFIG_PATH), exist_ok=True)
    with open(SENSOR_CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sensor_config, f, indent=2, ensure_ascii=False)

    # 5. 热重启 Sensor 线程池
    _hot_restart_sensors()

    empty_keys = [k for k, v in env_data.items() if v in (None, "")]
    auth_hint = (
        f"\n⚠️ 该 sensor 声明了 {len(empty_keys)} 个未填写的凭证（{', '.join(empty_keys)}），"
        f"热重启后它若发出鉴权求助消息，请转告用户到前端配置中心填写后再启用。"
        if empty_keys
        else ""
    )

    return (
        f"🎉 审批通过！Sensor '{sensor_name}' 成功合并。\n"
        f"📁 正式路径: {target_path}\n"
        f"🔬 协议体检: {verdict_text}\n"
        f"⚙️ 已写入 activate_sensor.json（enabled=true，含 {len(env_data)} 个环境变量声明），"
        f"系统正在后台热重启 Sensor 线程池。{auth_hint}\n"
        f"Git: {commit_msg}"
    )
