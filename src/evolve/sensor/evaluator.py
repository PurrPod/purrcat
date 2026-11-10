"""
Sensor 协议体检执行器 (evolve/sensor/evaluator.py)

宿主扮演网关（真网关夹具）拉起沙盒 sensor 子进程，把"宿主机真的能看见"的部分全部测掉：

  L0 静态契约：PEP 723 / stdout 重定向 / 无强制退出 / 无硬编码密钥 / env 声明交叉校验
  L1 协议夹具：握手时序 / stdout 纯净 / 缺凭证逼出失败上报 + sessionId 回填 / 抗污染 /
              错误响应 / 下发不崩 / 永不退出 / 杀后重启可拉起

检查实现分别在 checks_static / checks_runtime / fixtures；本模块只做编排与报告组装。
外部渠道不 mock，故出向投递内容、幂等去重、游标续传属真实链路（合并阶段人审），
报告末尾会显式列出「未覆盖项」，避免把"没测"伪装成"过了"。
"""

import json
import os
import threading

from src.utils.config import AGENT_VM_DIR

from src.evolve.common.paths import next_iteration_dir as _get_next_iteration_dir
from src.evolve.common.report import (
    now_iso as _now_iso,
    write_json as _write_json,
    write_report as _write_report,
)
from src.evolve.common.scoring import tally
from src.evolve.sensor.checks_runtime import runtime_checks as _runtime_checks
from src.evolve.sensor.checks_static import static_checks as _static_checks


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


def _summarize_cases(cases: list) -> dict:
    """汇总体检用例：只保留报告与 benchmark 需要的四个计数。"""
    agg = tally(cases)
    return {
        "passed": agg["passed"],
        "total": agg["total"],
        "errors": agg["errors"],
        "warnings": agg["warnings"],
    }


def _build_summary_block(counts: dict, H):
    errors_count, warns_count = counts["errors"], counts["warnings"]
    if errors_count:
        concl, tone = f"不通过：{errors_count} 项硬伤，{warns_count} 项告警", "accent"
    elif warns_count:
        concl, tone = f"通过但有告警：{warns_count} 项", "warn"
    else:
        concl, tone = "全部通过", "ok"

    return H.stats(
        [
            {
                "label": "体检结论",
                "value": "PASS" if not errors_count else "FAIL",
                "icon_name": "shield",
                "tone": tone,
                "desc": concl,
            },
            {
                "label": "通过",
                "value": f"{counts['passed']}/{counts['total']}",
                "icon_name": "check",
                "tone": "ok",
            },
            {
                "label": "错误",
                "value": str(errors_count),
                "icon_name": "x",
                "tone": "accent" if errors_count else "",
            },
            {
                "label": "告警",
                "value": str(warns_count),
                "icon_name": "alert",
                "tone": "warn" if warns_count else "",
            },
        ],
        cols=4,
    )


def _build_layer_blocks(cases: list, section_no: int, H) -> tuple:
    blocks = []
    for layer, title in (("L0", "L0 静态契约"), ("L1", "L1 协议夹具")):
        layer_cases = [c for c in cases if c["layer"] == layer]
        if not layer_cases:
            continue
        items = []
        for c in layer_cases:
            if c["pass"]:
                status, label = "pass", "通过"
            elif c["level"] == "warn":
                status, label = "warn", "告警"
            else:
                status, label = "fail", "硬伤"
            items.append(
                {
                    "title": c["title"],
                    "status": status,
                    "badge_text": label,
                    "notes": [c["detail"]],
                }
            )
        blocks.append(H.section(f"{section_no:02d}", title, H.cases(items)))
        section_no += 1
    return blocks, section_no


def _build_uncovered_block(config: dict, section_no: int, H):
    uncovered = list(_UNCOVERED)
    if config.get("source") == "local":
        uncovered.append(
            "该 sensor 声明 source: local（外部源可本地构造），"
            "可考虑为它补一条本地源闭环用例，把前 4 项未覆盖项也自动化。"
        )
    return H.section(
        f"{section_no:02d}",
        "未覆盖项（属真实链路，随 sensor_merge 人审）",
        H.bullets(uncovered),
    )


def _render_report(
    sensor_name: str,
    workplace_id: str,
    iteration_idx: int,
    config: dict,
    cases: list,
    iteration_dir: str,
) -> str:
    """渲染瑞士风 HTML 体检报告（报告即输出物，不列文件清单）。"""
    from src.evolve import report_html as H

    counts = _summarize_cases(cases)
    blocks = [_build_summary_block(counts, H)]
    layer_blocks, section_no = _build_layer_blocks(cases, 1, H)
    blocks.extend(layer_blocks)

    if not any(c["layer"] == "L1" for c in cases):
        blocks.append(
            H.note("L1 未执行（uv 不可用或进程拉起失败），协议面完全未覆盖。")
        )

    blocks.append(_build_uncovered_block(config, section_no, H))

    html = H.page(
        title=f"{sensor_name} · 协议体检报告",
        subtitle="宿主扮演真网关拉起 sensor 子进程实测的契约与协议结果；数据来自真跑，非 Agent 自报。",
        meta=[
            ("Sensor", sensor_name),
            ("迭代", f"Iteration {iteration_idx}"),
            ("工作区", f"sensor_workplace/{workplace_id}"),
            ("生成时间", _now_iso()),
        ],
        blocks=blocks,
        kicker="PURRCAT · SENSOR FACTORY",
        footer_left="Sensor Protocol Report",
        footer_right=f"Iteration {iteration_idx:02d}",
    )
    _write_report(iteration_dir, html)
    return html


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

    static_cases = _static_checks(script_text, config, config_error, sensor_name)
    runtime_cases, trace = _runtime_checks(
        script_path, workplace_root, declared, iteration_dir
    )
    cases = static_cases + runtime_cases

    # 取证三件套
    transcript_path = os.path.join(iteration_dir, "handshake.json")
    _write_json(transcript_path, trace.get("transcript", []))

    summary = _summarize_cases(cases)
    benchmark = {
        "sensor": sensor_name,
        "workplace_id": workplace_id,
        "iteration": iteration_idx,
        "summary": summary,
        "cases": cases,
    }
    _write_json(os.path.join(iteration_dir, "benchmark.json"), benchmark)

    _render_report(
        sensor_name, workplace_id, iteration_idx, config, cases, iteration_dir
    )

    return (
        f"🩺 协议体检完成：通过 {summary['passed']}/{summary['total']}"
        f"（错误 {summary['errors']} / 告警 {summary['warnings']}），"
        f"报告已生成（iteration-{iteration_idx}/report.html）。"
    )
