"""
Sensor 进化工厂核心逻辑 (evolve/sensor/factory.py)

单文件沙盒模式：Sensor 本体是单个 <name>.py（PEP 723 内联依赖），
沙盒内配套 sensor_config.json 作为合并注册的唯一依据。
"""

import json
import os
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
    """全新 sensor 的可运行骨架：鉴权求助 + 事件线程占位 + express 循环"""
    return f'''# /// script
# requires-python = ">=3.10"
# dependencies = [
#     # 在此声明依赖，如 "lark-oapi"
# ]
# ///

import sys
import json
import threading
import time
import os

# 🌟 铁律：stdout 是协议通道，print 日志必须全部转到 stderr
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr


def send_json_to_main(method: str, params: dict):
    _REAL_STDOUT.write(
        json.dumps({{"method": method, "params": params}}, ensure_ascii=False) + "\\n"
    )
    _REAL_STDOUT.flush()


def check_auth() -> bool:
    """首次启动鉴权检查：缺凭证必须发文字消息向 Agent 求助，严禁静默退出"""
    # TODO: 按实际情况替换凭证名
    token = os.environ.get("MY_TOKEN", "")
    if not token:
        send_json_to_main(
            "observe",
            {{"content": "[{sensor_name} 求助] 首次启动需要鉴权凭证 MY_TOKEN（当前为空）。"
             "请老板在前端配置中心 → Sensor 设置里为 {sensor_name} 填写 MY_TOKEN 后保存启用，"
             "我会在热重启后自动连接并保持待命。"}},
        )
        return False
    return True


def start_event_listener():
    """后台线程：连接外部服务，把事件 observe 给 Agent。此处为占位示例。"""

    def _worker():
        while True:
            try:
                # TODO: 替换为真实外部服务连接/监听逻辑
                time.sleep(3600)
            except Exception as e:
                print(f"❌ [{sensor_name}] 事件监听崩溃，5秒后重试: {{e}}")
                time.sleep(5)

    threading.Thread(target=_worker, daemon=True).start()


def handle_express(params: dict):
    """处理网关下发的 express：文本直接转发，文件类自行投递到外部渠道"""
    if params.get("type") == "file":
        import base64

        name = params.get("name", "file")
        data = base64.b64decode(params.get("content_b64", ""))
        print(f"📎 [{sensor_name}] 收到网关文件: {{name}} ({{len(data)}} bytes)")
        # TODO: 解码后发送到外部渠道（注意在后台线程执行网络请求）
        return

    message = params.get("message", "")
    kwargs = params.get("kwargs", {{}})
    print(f"💬 [{sensor_name}] 收到 Agent 回复: {{message}}")
    # TODO: 把 message 转发到外部渠道（注意在后台线程执行网络请求）


if not check_auth():
    # 凭证未就绪：仍保持进程存活，热重启读到新 env 后自动恢复
    pass

start_event_listener()

for line in sys.stdin:
    if not line.strip():
        continue
    try:
        req = json.loads(line)
        if req.get("method") == "express":
            handle_express(req["params"])
    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"❌ [{sensor_name}] 处理 express 异常: {{e}}")
'''


def _config_template(sensor_name: str) -> str:
    return json.dumps(
        {
            "name": sensor_name,
            "env": {"MY_TOKEN": ""},
            "capabilities": {"observe": True, "express": True},
            "tool_detail": False,
        },
        indent=2,
        ensure_ascii=False,
    )


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
            "capabilities": cfg.get("capabilities")
            or {"observe": True, "express": True},
            "tool_detail": cfg.get("tool_detail", False),
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

    _write_goal_and_guide(workplace_root, sensor_name, goal)

    sandbox_root = f"/agent_vm/sensor_workplace/{short_uuid}"
    return (
        f"【Sensor 工厂分配成功】工作区路径：{sandbox_root}（workplace_id: {short_uuid}）。\n"
        f"{action_msg}。\n"
        f"💡 提示：系统已在沙盒根目录为你生成了官方说明文档 GUIDE.md"
        f"（覆盖 stdio 协议/鉴权求助/文件收发/提交全流程），动手前请先通读！"
        f"注意：沙盒内可用 echo 管道手测，合并须通过 Request(sensor_merge) 获得老板批准。"
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


def sensor_request_handle(
    workplace_root: str, sensor_name: str, is_approved: bool
) -> str:
    """处理 Sensor 合并请求：拷贝正式目录 + 写 activate_sensor.json + 热重启"""
    if not is_approved:
        return f"人类拒绝了 {sensor_name} 的合并请求，已保留当前工作区供调整。"

    source_path = os.path.join(workplace_root, f"{sensor_name}.py")
    if not os.path.exists(source_path):
        return f"❌ 合并失败：沙盒中未找到 '{sensor_name}.py'，请补齐后再申请合并。"

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
    capabilities = sandbox_config.get("capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {"observe": True, "express": True}

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

    # 4. 注入 activate_sensor.json（enabled=true，env 空值留待老板填写）
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
        "capabilities": capabilities,
        "tool_detail": bool(sandbox_config.get("tool_detail", False)),
    }
    os.makedirs(os.path.dirname(SENSOR_CONFIG_PATH), exist_ok=True)
    with open(SENSOR_CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sensor_config, f, indent=2, ensure_ascii=False)

    # 5. 热重启 Sensor 线程池
    _hot_restart_sensors()

    empty_keys = [k for k, v in env_data.items() if v in (None, "")]
    auth_hint = (
        f"\n⚠️ 该 sensor 声明了 {len(empty_keys)} 个未填写的凭证（{', '.join(empty_keys)}），"
        f"热重启后它若发出鉴权求助消息，请转告老板到前端配置中心填写后再启用。"
        if empty_keys
        else ""
    )

    return (
        f"🎉 审批通过！Sensor '{sensor_name}' 成功合并。\n"
        f"📁 正式路径: {target_path}\n"
        f"⚙️ 已写入 activate_sensor.json（enabled=true，含 {len(env_data)} 个环境变量声明），"
        f"系统正在后台热重启 Sensor 线程池。{auth_hint}\n"
        f"Git: {commit_msg}"
    )
