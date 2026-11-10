"""KernelUpgrade(action='merge')：代发合并审批请求

Agent 只看到 KernelUpgrade，无法再直接向 Request 传 *_merge。
target 统一为 'uuid/名字'，定位唯一；对象不存在或产物不齐时本地拦截（不弹审批）。
"""

import os

from src.tool.utils.format import error_response, text_response
from src.tool.request.request_operations import submit_request
from src.utils.config import AGENT_VM_DIR
from .shared import MERGE_REQUEST_TYPES, parse_workplace_target

# 合并前必须齐备的产物（缺一即会在审批通过后合并失败，故本地先拦截）。
_MCP_CONFIG_FILE = "mcp_server_config.json"
_SENSOR_CONFIG_FILE = "sensor_config.json"


def _missing_error(t: str, target: str, name: str) -> str:
    return (
        f"❌ 未在沙盒工作区找到 {t} '{target}'（type / uuid / 名字可能有误）。\n"
        f"请先用 KernelUpgrade(action='create'|'upgrade', type='{t}', target='{name}') "
        "建立沙盒并完成开发后再申请合并。"
    )


def _artifact_error(t: str, target: str, artifact: str) -> str:
    return (
        f"❌ 沙盒中 {t} '{target}' 缺少合并必需产物 `{artifact}`：审批通过后也会合并失败，故此处直接拦截。\n"
        "请按沙盒内 GUIDE.md 补齐后重试。"
    )


def _audit(t: str, workplace_id: str, name: str) -> str | None:
    """返回本地拦截理由；None 表示对象存在且合并所需产物齐备。

    按 'uuid/名字' 直接定位（与审批侧解析方式一致），不再 glob 反查。
    """
    target = f"{workplace_id}/{name}"
    root = os.path.join(AGENT_VM_DIR, f"{t}_workplace", workplace_id)

    if t == "skill":
        return (
            None
            if os.path.isdir(os.path.join(root, name))
            else _missing_error(t, target, name)
        )

    if t == "mcp":
        if not os.path.isdir(os.path.join(root, name)):
            return _missing_error(t, target, name)
        # 合并唯一注册依据：<name>/mcp_server_config.json
        if not os.path.isfile(os.path.join(root, name, _MCP_CONFIG_FILE)):
            return _artifact_error(t, target, f"{name}/{_MCP_CONFIG_FILE}")
        return None

    if t == "sensor":
        # 本体是单文件 <name>.py，注册配置 sensor_config.json 位于工作区根
        if not os.path.isfile(os.path.join(root, f"{name}.py")):
            return _missing_error(t, target, name)
        if not os.path.exists(os.path.join(root, _SENSOR_CONFIG_FILE)):
            return _artifact_error(t, target, _SENSOR_CONFIG_FILE)
        return None

    if t == "agentloop":
        return (
            None
            if os.path.isfile(os.path.join(root, f"{name}.yaml"))
            else _missing_error(t, target, name)
        )

    if t == "graph":
        # Graph 本体是 <name>/ 文件夹（graph.json + asset/ 等随附文件整体拷贝）
        return (
            None
            if os.path.isfile(os.path.join(root, name, "graph.json"))
            else _missing_error(t, target, name)
        )

    return None


def merge_module(t: str, target: str) -> dict:
    req_type = MERGE_REQUEST_TYPES.get(t)
    if not req_type:
        return error_response(
            "ui-plugin 直接写盘即生效，无合并审批环节。",
            "❌ 无需合并",
        )

    tgt = (target or "").strip()
    if not tgt:
        return error_response(
            "执行失败：target 不能为空，应填 'uuid/名字'。",
            "❌ 参数错误",
        )
    pair = parse_workplace_target(tgt, strip=True)
    if not pair:
        return error_response(
            f"执行失败：target 格式不正确，应为 'uuid/名字'（工作区前缀 + 对象名）。当前输入为: '{target}'",
            "❌ 路径格式错误",
        )
    workplace_id, obj_name = pair
    audit_error = _audit(t, workplace_id, obj_name)
    if audit_error:
        return error_response(audit_error, "❌ 无法合并")

    result = submit_request(request_type=req_type, target=tgt, reason="")
    msg = (
        f"✅ 合并申请已提交给用户审批 (请求ID: {result['id']})。\n"
        f"申请类型: {req_type} | 目标: {target}\n\n"
        f"💡 系统指示：\n"
        f"1. 该合并需要用户 Yes/No 审批，请勿反复调用本工具催促。\n"
        f"2. 请挂起当前合并相关任务，等待系统通知（审批通过/拒绝）。\n"
        f"3. 若当前有其他无关联的独立任务，可继续执行。"
    )
    return text_response(msg, f"⏳ 合并申请已提交: {result['id']}")
