"""
Sensor 进化工厂核心逻辑 (evolve/sensor/factory.py)

单文件沙盒模式：Sensor 本体是单个 <name>.py（PEP 723 内联依赖），
沙盒内配套 sensor_config.json 作为合并注册的唯一依据。
"""

import json
import os
import shutil
import threading
import uuid
from datetime import datetime

from src.evolve.common.git import commit_paths, ensure_git_repo
from src.evolve.common.paths import latest_iteration_dir
from src.evolve.common.templates import write_goal_and_guide
from src.utils.config import (
    SENSOR_EXTENSION_DIR,
    SENSOR_CONFIG_PATH,
    AGENT_VM_DIR,
)

from .guide_generator import generate_sensor_guide


from .prompts import (
    build_sensor_config_template,
    build_sensor_gateway_probe,
    build_sensor_skeleton,
)


def _skeleton(sensor_name: str) -> str:
    return build_sensor_skeleton(sensor_name)


def _config_template(sensor_name: str) -> str:
    return build_sensor_config_template(sensor_name)


def _gateway_probe() -> str:
    return build_sensor_gateway_probe()


def _write_goal_and_guide(workplace_root: str, sensor_name: str, goal: str):
    write_goal_and_guide(workplace_root, goal, generate_sensor_guide(sensor_name, goal))


def _sandbox_sensor_names() -> set:
    """扫描全部进化沙盒，返回沙盒里已有 sensor 的名称集合。

    沙盒本体是各自根目录下单个 <name>.py（evals/、__pycache__ 等子目录天然被跳过），
    与 list_workplaces 的识别口径保持一致。
    """
    names: set = set()
    root = os.path.join(AGENT_VM_DIR, "sensor_workplace")
    if not os.path.isdir(root):
        return names
    for wid in os.listdir(root):
        w_path = os.path.join(root, wid)
        if not os.path.isdir(w_path):
            continue
        for item in os.listdir(w_path):
            if item.endswith(".py") and os.path.isfile(os.path.join(w_path, item)):
                names.add(item[:-3])
    return names


def sensor_factory_init(
    sensor_name: str, is_upgrade: bool, goal: str = ""
) -> tuple[str, str]:
    """初始化 Sensor 进化沙盒，返回 (系统提示, workplace_id)"""
    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = os.path.join(AGENT_VM_DIR, "sensor_workplace", short_uuid)
    script_path = os.path.join(workplace_root, f"{sensor_name}.py")

    # 同名唯一：新建时若正式目录/注册配置/任意进化沙盒里已有同名 sensor，直接拦回，
    # 避免同名多份互相抢占
    if not is_upgrade:
        from src.utils.config import get_sensor_config

        if (
            os.path.exists(os.path.join(SENSOR_EXTENSION_DIR, f"{sensor_name}.py"))
            or sensor_name in (get_sensor_config() or {})
            or sensor_name in _sandbox_sensor_names()
        ):
            return (
                f"❌ 已存在同名sensor：{sensor_name}，"
                f"如果是同一功能请直接在其基础上改进（改用 KernelUpgrade(action='upgrade', type='sensor')），"
                f"若是新sensor请重新命名防止冲突。",
                "",
            )

    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    os.makedirs(workplace_root, exist_ok=True)

    if is_upgrade:
        source = os.path.join(SENSOR_EXTENSION_DIR, f"{sensor_name}.py")
        if not os.path.exists(source):
            return f"❌ 无法执行升级：正式目录中未找到 '{sensor_name}.py'。", ""
        shutil.copy2(source, script_path)
        # 沿用现有注册配置（env/icon 已填的值不丢），缺则补模板
        from src.utils.config import get_sensor_config

        cfg = (get_sensor_config() or {}).get(sensor_name, {})
        config = {
            "name": sensor_name,
            "env": cfg.get("env") or {"MY_TOKEN": ""},
            "icon": cfg.get("icon", ""),
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
        action_msg = (
            f"已为你搭建了全新的 '{sensor_name}' 可运行骨架（含凭证校验与失败上报示例）"
        )

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
        f"（覆盖 stdio 协议/凭证与配置/失败上报/文件收发/提交全流程），动手前请先通读。"
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
    latest_dir, latest_idx = latest_iteration_dir(workplace_root)
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
                f"体检后又改动过 {', '.join(newer)}，证据已过期，需重跑 KernelUpgrade(action='test', type='sensor')",
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

    # 0. 协议体检：只作提醒，不再硬性拦截——体检未过/证据过期也照常合并，
    #    仅在结果里附一条建议重跑的提示，避免卡住用户主动发起的合并
    verdict_ok, verdict_text = _latest_protocol_verdict(workplace_root)

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
    ensure_git_repo(SENSOR_EXTENSION_DIR, "__pycache__/\n*.pyc\n", capture=True)
    commit_msg = (
        f"{'upgrade' if is_upgrade else 'add'} sensor {sensor_name} "
        f"{datetime.now().strftime('%Y-%m-%d')}"
    )
    commit_paths(SENSOR_EXTENSION_DIR, [f"{sensor_name}.py"], commit_msg, capture=True)

    # 4. 注入 activate_sensor.json（enabled=true；env 取沙盒实填值，留空键保留正式配置里的旧值）
    sensor_config = {}
    if os.path.exists(SENSOR_CONFIG_PATH):
        try:
            with open(SENSOR_CONFIG_PATH, "r", encoding="utf-8") as f:
                sensor_config = json.load(f)
        except Exception:
            pass
    prev_entry = sensor_config.get(sensor_name)
    if not isinstance(prev_entry, dict):
        prev_entry = {}
    prev_env = prev_entry.get("env")
    if not isinstance(prev_env, dict):
        prev_env = {}

    # 沙盒里填了真实值的键直接生效；留空的键沿用上次已填好的值，避免每次合并都把凭证清空重填
    merged_env = {}
    for k, v in env_data.items():
        merged_env[k] = v if v not in (None, "") else prev_env.get(k, v)

    sensor_config[sensor_name] = {
        "enabled": True,
        "env": merged_env,
        "icon": sandbox_config.get("icon") or prev_entry.get("icon", ""),
        "tool_detail": bool(sandbox_config.get("tool_detail", False)),
        "source": sandbox_config.get("source", "remote"),
    }
    os.makedirs(os.path.dirname(SENSOR_CONFIG_PATH), exist_ok=True)
    with open(SENSOR_CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sensor_config, f, indent=2, ensure_ascii=False)

    # 5. 热重启 Sensor 线程池
    _hot_restart_sensors()

    empty_keys = [k for k, v in merged_env.items() if v in (None, "")]
    auth_hint = (
        f"\n⚠️ 漏配告警：{len(empty_keys)} 个凭证在合并时仍为空（{', '.join(empty_keys)}）——"
        f"凭证本应在申请合并前就填好，现在该 sensor 会持续上报失败。请引导用户立即补齐。"
        if empty_keys
        else ""
    )

    verdict_note = (
        f"🔬 协议体检: {verdict_text}"
        if verdict_ok
        else f"⚠️ 协议体检提醒（不阻止合并）: {verdict_text}；建议重跑 KernelUpgrade(action='test', type='sensor') 后再发布"
    )

    return (
        f"🎉 审批通过！Sensor '{sensor_name}' 成功合并。\n"
        f"📁 正式路径: {target_path}\n"
        f"{verdict_note}\n"
        f"⚙️ 已写入 activate_sensor.json（enabled=true，含 {len(merged_env)} 个环境变量声明），"
        f"系统正在后台热重启 Sensor 线程池。{auth_hint}\n"
        f"Git: {commit_msg}"
    )
