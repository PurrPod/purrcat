"""ComputerUse 工具主入口 - 参数校验与调度"""

import traceback
import time
import json
import os

from src.tool.computeruse.executor import execute_action
from src.tool.computeruse.exceptions import ComputerUseError
from src.tool.computeruse.cursor_manager import notify_ai_active
from src.tool.utils.format import error_response, text_response, warning_response
from src.utils.config import DATA_DIR

# 新增引入 submit_request 用于自动发起审批
from src.tool.request.request_operations import submit_request


def _check_computer_use_auth() -> bool:
    """检查当前是否有有效的 ComputerUse 权限授权"""
    try:
        auth_file = os.path.join(
            DATA_DIR, "checkpoints", "agent", "computer_use_auth.json"
        )
        if not os.path.exists(auth_file):
            return False
        with open(auth_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return time.time() < data.get("expire_at", 0)
    except Exception:
        return False


def ComputerUse(
    action: str,
    coordinate: list = None,
    element_id: str = None,
    text: str = None,
    keep_apps: list = None,
    scroll_amount: int = 0,
    wait_time: float = 0.1,
    **kwargs,
) -> str | dict:
    try:
        action = action.strip().lower() if action else ""

        if action in [
            "mouse_move",
            "left_click",
            "right_click",
            "double_click",
            "left_click_drag",
        ]:
            if not coordinate and not element_id:
                return error_response(
                    f"缺少 coordinate 或 element_id，操作: {action}", "❌ 缺少目标"
                )

        if action in ["type", "key", "find_element", "launch_app"] and not text:
            return error_response(f"缺少文本参数 text，操作: {action}", "❌ 缺少文本")

        # 🌟 权限检查：验证是否有有效的 ComputerUse 授权
        if not _check_computer_use_auth():
            # 【修改点】：直接自动发起申请，不再要求 Agent 自己调 Request 工具
            reason_str = f"系统自动拦截：Agent 尝试执行 '{action}' 物理电脑操作，但当前缺少授权。"
            req_result = submit_request(
                request_type="computer_use", target="system", reason=reason_str
            )

            # 话术设计：明确告知 Agent 申请已自动提交，请勿重试并挂起任务
            msg = (
                f"⏳ 权限不足，已自动向老板提交了 ComputerUse 控制权限申请 (请求ID: {req_result['id']})。\n\n"
                f"💡 系统指示：\n"
                f"1. 该权限需要老板进行 Yes/No 审批，请勿反复调用本工具催促。\n"
                f"2. 强依赖此项权限的工作流请暂时挂起，等待后续系统发送通知（审批通过/拒绝）后再继续。\n"
                f"3. 若当前有其他无强关联的独立任务（如查阅文档、整理数据），你可以先执行其他任务。"
            )
            return warning_response(msg, f"⏳ 已自动申请权限: {req_result['id']}")

        # 👇 添加这一行：通知 AI 正在控制鼠标 👇
        notify_ai_active()

        # 调度执行
        result = execute_action(
            action,
            coordinate=coordinate,
            element_id=element_id,
            text=text,
            keep_apps=keep_apps,
            scroll_amount=scroll_amount,
            wait_time=wait_time,
        )

        # 截图多模态返回
        if action == "screenshot":
            if not result.get("base64"):  # 被死循环检测拦截
                return warning_response(result["message"], "⚠️ 截图被拦截")

            ui_elements = result.get("ui_elements", "")
            ocr_hint = f"{result['message']}\n💡 图中已打好数字标签(SoM)，请直接使用 `element_id` 进行点击！\n[元素对照表]:\n{ui_elements}"

            return {
                "content": {"type": "image", "data": result["base64"], "ext": ".png"},
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "text",
                    "snip": ocr_hint,
                },
            }

        return text_response(result.get("message", "操作已完成"), f"✅ {action} 成功")

    except ComputerUseError as e:
        return warning_response(str(e), f"⚠️ {action} 失败")
    except Exception as e:
        traceback.print_exc()
        return error_response(f"系统异常: {str(e)}", "❌ 致命异常")
