"""KernelUpgrade(action='test')：代发/直跑架构级测试

全部免审（除 skill 盲测需用户批准外）：
- skill：代发 skill_test（Trigger 免审 + 盲测审批）
- sensor：代发 sensor_test（宿主扮网关体检）
- mcp：直接后台并发评测（需先产出 schema_dump.json）
- agentloop / graph：宿主侧直跑静态三重校验（与合并网关同一套权威校验）
- ui-plugin：无架构级测试，需 Agent 沙盒自测
"""

import os

from src.tool.utils.format import error_response, text_response
from src.tool.request.request_operations import submit_request
from src.utils.config import AGENT_VM_DIR
from src.utils.graph_api import graph_file
from src.evolve import run_mcp_eval_background
from .shared import parse_workplace_target


def test_module(t: str, target: str) -> dict:
    if t == "skill":
        return _test_skill(target)
    if t == "sensor":
        return _test_sensor(target)
    if t == "mcp":
        return _test_mcp(target)
    if t == "agentloop":
        return _test_agentloop(target)
    if t == "graph":
        return _test_graph(target)
    return error_response(
        "❌ UI 插件无架构级测试：请在沙盒中自测（刷新页面验证交互），确认无误后告知用户。",
        "❌ 无架构级测试",
    )


def _test_skill(target: str) -> dict:
    from src.tool.request.request import _validate_skill_test

    err = _validate_skill_test(target)
    if err:
        return error_response(*err)

    has_graph = os.path.exists(graph_file("skill_eval"))
    result = submit_request(
        request_type="skill_test",
        target=target,
        reason="",
        extra={"trigger_started": False, "has_graph": has_graph},
    )

    trigger_note = (
        "🎯 Trigger 激发测试无需审批，系统即将自动启动，完成后通过系统级通知汇报结果。"
    )
    if not has_graph:
        trigger_note += (
            "\n⚠️ 注意：本地无 skill test 的图（图库缺少 skill_eval 测试图），将跳过后台盲测；"
            "如需完整盲测，请用户先安装 skill_eval 测试图，再重新提交申请。"
        )
        blind_note = ""
    else:
        blind_note = (
            "\n✅ 后台盲测申请已提交用户审批，获批后系统将自动在后台运行，"
            "期间请挂起等待，禁止轮询。"
        )
    uuid = target.split("/")[0]
    artifact_note = (
        f"\n📁 产物目录：`/agent_vm/skill_workplace/{uuid}/iteration-N/`"
        "（N 为迭代序号；内含 trigger_result.json、eval_result.json、benchmark.json、report.html）"
    )
    return text_response(
        f"{trigger_note}{blind_note}{artifact_note}",
        f"⏳ skill_test 已受理: {result['id']}",
    )


def _test_sensor(target: str) -> dict:
    from src.tool.request.request import _validate_sensor_test

    err = _validate_sensor_test(target)
    if err:
        return error_response(*err)

    result = submit_request(
        request_type="sensor_test",
        target=target,
        reason="",
        extra={"eval_started": False},
    )
    uuid = target.split("/")[0]
    return text_response(
        "🔬 Sensor 协议体检无需审批，系统即将自动启动（宿主亲自扮演网关实跑你的 sensor），"
        "完成后通过系统级通知汇报结果。\n"
        "💡 体检全绿后才能申请合并；若改动了代码，务必重跑本体检。"
        f"\n📁 产物目录：`/agent_vm/sensor_workplace/{uuid}/iteration-N/`"
        "（N 为迭代序号；内含 benchmark.json、handshake.json、report.html、sensor_stderr.log）",
        f"⏳ sensor_test 已受理: {result['id']}",
    )


def _test_mcp(target: str) -> dict:
    """MCP 测试：宿主侧重跑沙盒内的并发评测（需先产出 schema_dump.json）"""
    pair = parse_workplace_target(target)
    if not pair:
        return error_response(
            f"执行失败：target 格式不正确，应为 'uuid/mcp_name'。当前输入为: '{target}'",
            "❌ 路径格式错误",
        )
    workplace_id, mcp_name = pair

    mcp_dir = os.path.join(AGENT_VM_DIR, "mcp_workplace", workplace_id, mcp_name)
    if not os.path.isdir(mcp_dir):
        return error_response(
            f"执行被拒绝：未找到沙盒工作区 '{target}'，请确认 workplace_id 与 MCP 名无误。",
            "❌ 沙盒不存在",
        )
    evals_file = os.path.join(mcp_dir, "evals", "evals.json")
    if not os.path.exists(evals_file):
        return error_response(
            "❌ 执行被拒绝：沙盒内未找到 `evals/evals.json`，测试流水线无用例可跑。\n"
            "请先编写测试用例再申请测试。",
            "❌ 缺少测试用例",
        )

    schema_path = os.path.join(mcp_dir, "evals", "outputs", "schema_dump.json")
    if not os.path.exists(schema_path):
        return error_response(
            "❌ 执行被拒绝：未检测到测试前置产物！\n\n"
            "由于当前 MCP 还处于沙盒开发期，你必须先亲自在沙盒里测试 scripts/evaluation.py 能否跑通！\n"
            "只有当上述脚本成功执行，并生成了 `evals/outputs/schema_dump.json` 之后，你才有资格调用测试！",
            "❌ 缺失前置产物",
        )

    stale_warning = _stale_schema_warning(schema_path)
    from src.agent.manager import manager

    run_mcp_eval_background(workplace_id, mcp_name, manager.get_active_session_id())

    msg = (
        f"🚀 MCP '{mcp_name}' 的并发测试流水线已在后台启动！\n"
        f"💡 提示：测试完成后系统会主动推送结果报告，请耐心等待系统级通知。\n"
        f"📁 产物目录：`/agent_vm/mcp_workplace/{workplace_id}/{mcp_name}/iteration-N/`"
        "（N 为迭代序号；内含 report.html，沙盒 evals/outputs/ 的快照与执行结果会一并归档）"
    )
    if stale_warning:
        msg = f"{stale_warning}\n\n{msg}"
    return text_response(msg, f"⏳ {mcp_name} 宿主机评测中")


def _stale_schema_warning(schema_path: str) -> str:
    """过期提醒（不拦截）：schema_dump 可能是旧代码生成的、会静默假绿。
    比对"快照时间"与"最近源码(含 evals.json)时间"，快照更旧时在返回消息里提醒，
    让 Agent 自行判断是否重跑刷新。"""
    mcp_dir = os.path.abspath(os.path.join(schema_path, "..", "..", ".."))
    schema_mtime = os.path.getmtime(schema_path)

    skip = (".venv", "venv", "__pycache__", "node_modules", ".git", "scripts")
    newest_src = 0.0
    for dirpath, dirnames, filenames in os.walk(mcp_dir):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn.endswith(".py"):
                newest_src = max(
                    newest_src, os.path.getmtime(os.path.join(dirpath, fn))
                )
    evals_json = os.path.join(mcp_dir, "evals", "evals.json")
    if os.path.exists(evals_json):
        newest_src = max(newest_src, os.path.getmtime(evals_json))

    if schema_mtime < newest_src:
        return (
            "⚠️ **注意：测试快照可能已过期！**\n"
            "源码/工具描述相较 `schema_dump.json` 有新改动，当前快照可能仍是旧代码生成的，"
            "报告会用旧描述渲染。若确实改了描述/逻辑，请先在沙盒重跑 "
            "`python scripts/evaluation.py` 刷新快照后再测；若改动无关描述，可忽略本提醒。"
        )
    return ""


# ==========================================
# agentloop / graph：宿主侧静态校验（免审，与合并网关同一套权威校验）
# ==========================================
def _split_workplace(target: str) -> tuple[str, str] | None:
    return parse_workplace_target(target)


def _test_agentloop(target: str) -> dict:
    pair = _split_workplace(target)
    if not pair:
        return error_response(
            f"执行失败：target 应为 'uuid/范式名'。当前输入为: '{target}'",
            "❌ 路径格式错误",
        )
    workplace_id, name = pair

    from src.evolve.agentloop.validator import validate_agentloop_file

    yaml_path = os.path.join(
        AGENT_VM_DIR, "agentloop_workplace", workplace_id, f"{name}.yaml"
    )
    if not os.path.exists(yaml_path):
        return error_response(
            f"❌ 沙盒中未找到 '{name}.yaml'（{yaml_path}）。请确认 target 与工作区一致。",
            "❌ 文件不存在",
        )
    report = validate_agentloop_file(yaml_path, expected_name=name)
    return _format_validation_report("agentloop", name, target, report)


def _test_graph(target: str) -> dict:
    pair = _split_workplace(target)
    if not pair:
        return error_response(
            f"执行失败：target 应为 'uuid/图名'。当前输入为: '{target}'",
            "❌ 路径格式错误",
        )
    workplace_id, name = pair

    from src.evolve.graph.validator import validate_graph_folder

    folder = os.path.join(AGENT_VM_DIR, "graph_workplace", workplace_id, name)
    if not os.path.exists(os.path.join(folder, "graph.json")):
        return error_response(
            f"❌ 沙盒中未找到 '{name}/graph.json'（{folder}）。请确认 target 与工作区一致。",
            "❌ 文件不存在",
        )
    report = validate_graph_folder(folder, expected_name=name)
    return _format_validation_report("graph", name, target, report)


def _format_validation_body(kind: str, name: str, target: str, report: dict) -> str:
    """铺开校验报告正文，不含工具响应包装。"""
    checks = report.get("checks", [])
    errs = [c for c in checks if c["level"] == "error" and not c["ok"]]
    warns = [c for c in checks if c["level"] == "warn" and not c["ok"]]

    uuid = target.split("/")[0]
    if kind == "graph":
        report_path = (
            f"/agent_vm/graph_workplace/{uuid}/{name}/evals/outputs/validation.json"
        )
    else:
        report_path = (
            f"/agent_vm/agentloop_workplace/{uuid}/evals/outputs/validation.json"
        )
    artifact_note = (
        "\n📁 产物目录：本次校验由宿主侧直接执行、不向沙盒写文件；"
        f"你在沙盒自跑校验脚本时，报告落在 `{report_path}`。"
    )

    if report.get("ok"):
        body = (
            f"✅ {kind} '{name}' 校验通过（错误 0，警告 {len(warns)}）。\n"
            f"宿主合并网关会重跑同一套校验（防篡改），可直接申请合并。"
        )
    else:
        lines = [
            f"❌ {kind} '{name}' 校验未通过（{len(errs)} 处错误，{len(warns)} 处警告）："
        ]
        for c in errs[:20]:
            detail = f" —— {c['detail']}" if c.get("detail") else ""
            lines.append(f"- ✗ {c['title']}{detail}")
        if len(errs) > 20:
            lines.append(f"- …另有 {len(errs) - 20} 处错误")
        lines.append(
            f"\n修正后重跑 KernelUpgrade(action='test', type='{kind}', target='{target}')；全绿后再申请合并。"
        )
        body = "\n".join(lines)

    return body + artifact_note


def _format_validation_report(kind: str, name: str, target: str, report: dict) -> dict:
    """把宿主侧校验报告铺开给 Agent（免审，与合并网关同一事实来源）。"""
    body = _format_validation_body(kind, name, target, report)
    snip = f"{'✅' if report.get('ok') else '❌'} {kind} {name} 校验"
    return text_response(body, snip)
