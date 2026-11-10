"""Request 工具的纯文案与目标解析。

与审批 I/O 解耦，便于验证拒绝/放行文案是否与旧版一致。
"""

from __future__ import annotations

MERGE_REQUEST_TYPES = (
    "skill_merge",
    "mcp_merge",
    "sensor_merge",
    "agentloop_merge",
    "graph_merge",
)

# 这些类型批准后由后台任务接管，不需要再自动下发文件权限
AUTO_PERMISSION_EXEMPT_TYPES = ("skill_test", "sensor_test") + MERGE_REQUEST_TYPES


def build_request_record(
    request_type: str,
    target: str,
    reason: str,
    req_id: str,
    created_at: str,
    extra: dict | None = None,
) -> dict:
    """构造持久化到 requests.json 的请求记录；extra 覆盖同名字段。"""
    record = {
        "id": req_id,
        "type": request_type,
        "target": target,
        "reason": reason,
        "status": "pending",  # 固定初始状态，等待人类给出 yes/no
        "created_at": created_at,
    }
    if extra:
        record.update(extra)
    return record


def split_merge_target(target: str) -> tuple[str, str]:
    """合并目标统一为 'uuid/名字'，返回 (workplace_id, name)。"""
    workplace_id, _, name = (target or "").partition("/")
    return workplace_id.strip(), name.strip()


def normalize_target_path(target: str) -> str:
    return target.replace("\\", "/")


def format_rejection_feedback(req_type: str, feedback: str) -> str:
    """按请求类型包装拒绝理由；未登记的类型原样返回。"""
    if req_type == "skill_test":
        return (
            "用户拒绝了测试申请，请根据以下原因调整沙盒代码或测试用例后再次申请：\n"
            f"【拒绝理由】: {feedback}"
        )
    if req_type == "sensor_test":
        return (
            "用户拒绝了协议体检申请，请根据以下原因调整沙盒代码或 sensor_config.json 后再次申请：\n"
            f"【拒绝理由】: {feedback}"
        )
    if req_type in MERGE_REQUEST_TYPES:
        return (
            "用户拒绝了代码合并请求，请在沙盒工厂中根据以下原因继续修复：\n"
            f"【拒绝理由】: {feedback}"
        )
    return feedback


def build_decision_callback(
    req_id: str, target: str, approved: bool, req_type: str, feedback: str
) -> str:
    """构造回推给 Agent 的系统通知；普通授权通过时追加自动下发提示。"""
    decision_text = "【同意并已生效】" if approved else "【被拒绝】"
    message = (
        f"🔔 【系统通知】请求 (ID: {req_id}) | 目标: {target} | 结果: {decision_text}\n"
        f"系统反馈/批注: {feedback}"
    )
    if approved and req_type not in AUTO_PERMISSION_EXEMPT_TYPES:
        message += "\n系统已为你自动下发权限，请直接继续执行被挂起的任务。"
    return message
