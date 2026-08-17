"""Request 工具主入口 - 向人类发起审批请求"""

import os
import traceback

from src.tool.request.request_operations import submit_request
from src.tool.utils.format import error_response, text_response
from src.utils.config import GRAPHS_DIR, AGENT_VM_DIR


def _validate_skill_test(target: str) -> tuple[str, str] | None:
    """skill_test 前置校验：沙盒工作区与 evals.json 是否齐备（图库缺图不拦截，仅跳过盲测）"""
    parts = target.split("/")
    if len(parts) != 2 or not all(parts):
        return (
            f"执行失败：target 格式不正确，应为 'uuid/技能名'。当前输入为: '{target}'",
            "❌ 路径格式错误",
        )

    workplace_id, skill_name = parts

    # 前置校验：沙盒工作区与测试用例必须存在
    workplace_skill_dir = os.path.join(
        AGENT_VM_DIR, "skill_workplace", workplace_id, skill_name
    )
    if not os.path.exists(workplace_skill_dir):
        return (
            f"执行被拒绝：未找到沙盒工作区 '{target}'，请确认 workplace_id 与技能名无误。",
            "❌ 沙盒不存在",
        )
    if not os.path.exists(os.path.join(workplace_skill_dir, "evals", "evals.json")):
        return (
            f"执行被拒绝：沙盒 '{target}' 内未找到 evals/evals.json，请先编写测试用例再申请测试。",
            "❌ 缺少测试用例",
        )

    return None


def Request(request_type: str, target: str, reason: str, **kwargs) -> str:
    """
    向人类（老板）发起审批请求。

    适用场景：
    - 权限拦截：读写宿主机文件、操作物理电脑
    - 能力缺失：需下载 mcp/skill/sensor/graph
    - 技能盲测：沙盒开发完毕后申请 skill_test，获批后由系统自动运行

    提交后会等待老板的 Yes/No 审批，期间可挂起或执行其他独立任务。
    """
    try:
        valid_types = [
            "mcp_install",
            "skill_install",
            "file_write",
            "file_read",
            "sensor_install",
            "graph_install",
            "computer_use",
            "skill_test",  # Skill 盲测：批准后由系统自动运行
            "skill_merge",  # 保留：合并代码仍需审批
            "mcp_merge",  # 新增：MCP 代码合并
        ]

        if request_type not in valid_types:
            return error_response(
                f"不支持的 request_type: {request_type}", "❌ 参数错误"
            )

        if request_type == "skill_test":
            err = _validate_skill_test(target)
            if err:
                return error_response(*err)

            # 🌟 统一入队：Trigger 免审测试由主进程轮询接管自动启动（工具运行在隔离子进程，
            # 此处不能直接起后台线程，否则线程会随子进程退出被杀）
            has_graph = os.path.exists(os.path.join(GRAPHS_DIR, "skill_eval.json"))
            result = submit_request(
                request_type=request_type,
                target=target,
                reason=reason,
                extra={"trigger_started": False, "has_graph": has_graph},
            )

            trigger_note = (
                "🎯 Trigger 激发测试无需审批，系统即将自动启动，完成后通过系统级通知汇报结果。"
                if has_graph
                else "🎯 Trigger 激发测试无需审批，系统即将自动启动，完成后通过系统级通知汇报结果。\n"
                "⚠️ 注意：本地无 skill test 的图（图库缺少 skill_eval.json），将跳过后台盲测；"
                "如需完整盲测，请老板先安装 skill_eval 测试图，再重新提交 skill_test 申请。"
            )
            blind_note = (
                "\n✅ 后台盲测申请已提交老板审批，获批后系统将自动在后台运行，期间请挂起等待，禁止轮询。"
                if has_graph
                else ""
            )
            msg = f"{trigger_note}{blind_note}"
            return text_response(msg, f"⏳ skill_test 已受理: {result['id']}")

        result = submit_request(
            request_type=request_type,
            target=target,
            reason=reason,
        )

        # 话术设计：告诉大模型请求已经进入审批队列，不要重试，自己安排接下来的时间
        msg = (
            f"✅ 申请已成功提交给老板审批 (请求ID: {result['id']})。\n"
            f"请求类型: {request_type} | 目标: {target}\n\n"
            f"💡 系统指示：\n"
            f"1. 该操作需要老板进行 Yes/No 审批，请勿反复调用本工具催促。\n"
            f"2. 强依赖此项权限或能力的工作流请暂时挂起，等待后续系统发送通知（审批通过/拒绝）。\n"
            f"3. 若当前有其他与此请求无强关联的独立任务（如查阅其他文档、整理现有数据），你可以继续执行。"
        )

        return text_response(msg, f"⏳ 申请已提交: {result['id']}")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"提交申请异常: {str(e)}", "❌ 提交失败")
