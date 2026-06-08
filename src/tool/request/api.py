"""Request 工具 API 层 - 高内聚的 API 逻辑，提供给前端调用"""

import json
import os
import time

from src.tool.request.request_operations import REQUESTS_FILE, REQUEST_LOCK


def get_pending_requests() -> list:
    """获取所有待老板审批的请求"""
    if not os.path.exists(REQUESTS_FILE):
        return []

    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return []

    pending_list = [req for req in data.values() if req.get("status") == "pending"]
    pending_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return pending_list


def resolve_request(req_id: str, approved: bool, feedback: str = "", ignore: bool = False) -> dict:
    """
    处理请求

    Args:
        req_id: 请求ID
        approved: 是否批准
        feedback: 老板附加批注
        ignore: 如果为 True，静默关闭，不通知 Agent

    Returns:
        处理结果字典
    """
    if not os.path.exists(REQUESTS_FILE):
        return {"status": "error", "message": "请求记录文件不存在"}

    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return {"status": "error", "message": "请求记录解析失败"}

        if req_id not in data:
            return {"status": "error", "message": f"找不到请求 ID: {req_id}"}

        req = data[req_id]
        if req["status"] != "pending":
            return {"status": "error", "message": f"该请求已被处理过: {req['status']}"}

        # 1. 更新状态
        if ignore:
            req["status"] = "ignored"
        else:
            req["status"] = "approved" if approved else "rejected"

        req["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        req["feedback"] = feedback

        # 2. 存盘
        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # 3. 构造幽灵注入消息 (如果是 ignore 则静默跳过)
    if ignore:
        return {"status": "success", "message": f"请求 {req_id} 已静默忽略。"}

    decision_text = "【同意(Approved)】" if approved else "【拒绝(Rejected)】"
    target = req.get("target", "未知目标")
    req_type = req.get("type", "未知类型")

    msg_lines = [
        f"🔔 【系统通知：老板审批结果下发】",
        f"您之前提交的请求 (ID: {req_id}) 已处理。",
        f"申请类型: {req_type} | 目标: {target}",
        f"老板审批结果: {decision_text}",
    ]

    if feedback.strip():
        msg_lines.append(f"老板附加批注: {feedback.strip()}")

    if approved:
        msg_lines.append("你可以利用刚刚获批的权限或资源，继续执行之前被挂起的任务了。")
    else:
        msg_lines.append("请求被拒绝，请放弃该路径，尝试寻找其他替代方案，或向老板汇报任务无法推进。")

    callback_msg = "\n".join(msg_lines)
    
    from src.agent import agent_force_push
    agent_force_push(callback_msg, type="system")

    return {"status": "success", "message": f"请求已处理，并已将结果通知 Agent。"}


def get_resolved_requests() -> list:
    """获取所有已处理完毕的请求"""
    if not os.path.exists(REQUESTS_FILE):
        return []
    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return []
    
    resolved_list = [req for req in data.values() if req.get("status") != "pending"]
    resolved_list.sort(key=lambda x: x.get("resolved_at", x.get("created_at", "")), reverse=True)
    return resolved_list


def delete_request(req_id: str) -> bool:
    """把请求从记录文件中彻底踢出（物理删除）"""
    if not os.path.exists(REQUESTS_FILE):
        return False
    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if req_id in data:
                del data[req_id]
                with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
        except Exception:
            pass
    return False