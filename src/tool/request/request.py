"""Request 工具主入口 - 向人类发起审批请求"""

import traceback

from src.tool.request.request_operations import submit_request
from src.tool.utils.format import error_response, text_response


def Request(request_type: str, target: str, reason: str, **kwargs) -> str:
    """
    向人类（老板）发起审批请求。

    适用场景：
    - 权限拦截：读写宿主机文件
    - 能力缺失：需下载 mcp/skill/sensor/graph

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
        ]

        if request_type not in valid_types:
            return error_response(f"不支持的 request_type: {request_type}", "❌ 参数错误")

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

        return text_response({"req_id": result["id"], "status": "pending"}, msg)

    except Exception as e:
        traceback.print_exc()
        return error_response(f"提交申请异常: {str(e)}", "❌ 提交失败")