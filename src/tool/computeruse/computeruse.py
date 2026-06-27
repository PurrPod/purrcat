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
            return error_response(
                '当前没有操作物理电脑的权限，请先向老板发起申请。\n\n使用方式：\n```python\nRequest(\n    request_type="computer_use",\n    target="system",\n    reason="需要操作电脑完成XX任务，预计需要X分钟"\n)\n```',
                "⚠️ 权限拦截",
            )

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
