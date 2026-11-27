"""Request 工具主入口 - 向人类发起审批请求"""

import os
import traceback

from src.tool.request.request_operations import submit_request
from src.tool.utils.format import error_response, text_response
from src.utils.config import AGENT_VM_DIR


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


def _validate_sensor_test(target: str) -> tuple[str, str] | None:
    """sensor_test 前置校验：插件包 <name>/ 内的 py 与 sensor_config.json 是否齐备"""
    parts = target.split("/")
    if len(parts) != 2 or not all(parts):
        return (
            f"执行失败：target 格式不正确，应为 'uuid/传感器名'。当前输入为: '{target}'",
            "❌ 路径格式错误",
        )

    workplace_id, sensor_name = parts
    plugin_dir = os.path.join(
        AGENT_VM_DIR, "sensor_workplace", workplace_id, sensor_name
    )

    if not os.path.exists(os.path.join(plugin_dir, f"{sensor_name}.py")):
        return (
            f"执行被拒绝：未找到沙盒传感器 '{sensor_name}.py'，请确认 workplace_id 与传感器名无误。",
            "❌ 沙盒不存在",
        )
    if not os.path.exists(os.path.join(plugin_dir, "sensor_config.json")):
        return (
            f"执行被拒绝：沙盒 '{target}' 内未找到 sensor_config.json（合并注册的唯一依据），"
            "请先按 GUIDE.md 第 6 节补齐。",
            "❌ 缺少注册配置",
        )

    return None


def Request(request_type: str, target: str, reason: str, **kwargs) -> str:
    """
    向人类（用户）发起审批请求。

    适用场景：
    - 权限拦截：读写宿主机文件（file_read / file_write）

    注意：进化工厂的测试与合并已从本工具剥离，改由 KernelUpgrade 工具代发
    （KernelUpgrade(action='test'/'merge', type=..., target=...)），此处不再接受
    skill_test / sensor_test / *_merge 等类型。

    提交后会等待用户的 Yes/No 审批，期间可挂起或执行其他独立任务。
    """
    try:
        valid_types = [
            "file_write",
            "file_read",
        ]

        if request_type not in valid_types:
            return error_response(
                f"不支持的 request_type: {request_type}。"
                "进化工厂的测试与合并请改用 KernelUpgrade(action='test'/'merge', type=..., target=...)。",
                "❌ 参数错误",
            )

        result = submit_request(
            request_type=request_type,
            target=target,
            reason=reason,
        )

        # 话术设计：告诉大模型请求已经进入审批队列，不要重试，自己安排接下来的时间
        msg = (
            f"✅ 申请已成功提交给用户审批 (请求ID: {result['id']})。\n"
            f"请求类型: {request_type} | 目标: {target}\n\n"
            f"💡 系统指示：\n"
            f"1. 该操作需要用户进行 Yes/No 审批，请勿反复调用本工具催促。\n"
            f"2. 强依赖此项权限或能力的工作流请暂时挂起，等待后续系统发送通知（审批通过/拒绝）。\n"
            f"3. 若当前有其他与此请求无强关联的独立任务（如查阅其他文档、整理现有数据），你可以继续执行。"
        )

        return text_response(msg, f"⏳ 申请已提交: {result['id']}")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"提交申请异常: {str(e)}", "❌ 提交失败")
