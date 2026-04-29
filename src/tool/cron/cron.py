"""Cron 工具主入口 - 统一调度 list、add、delete、update 操作"""

import traceback
import re
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.cron.exceptions import CronError
from src.tool.cron.cron_operations import add_cron, delete_cron, update_cron, list_crons


def Cron(action: str, name: str = None, trigger_time: str = None,
         repeat_rule: str = None, active: bool = None, **kwargs) -> str:
    """
    Cron 工具主入口函数，支持四种操作：list、add、delete、update
    
    Args:
        action: 操作类型，必须为 "list"、"add"、"delete" 或 "update"
        name: 闹钟名称/标题（add 和 update 操作时必填）
        trigger_time: 触发时间，HH:MM 格式（add 和 update 操作时使用）
        repeat_rule: 重复规则，默认 "none"
            - "none": 不重复
            - "everyday": 每天
            - "weekly_1" ~ "weekly_7": 每周一到周日
        active: 是否激活（update 操作时使用）
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        if not action:
            return error_response(
                "缺少必需参数 'action'。引导：请提供你想执行的操作类型，可选值为：'list'(查询所有)、'add'(添加)、'delete'(删除)、'update'(修改)。",
                "缺少 action"
            )

        action = str(action).strip().lower()
        if action not in ["list", "add", "delete", "update"]:
            return error_response(f"无效的 action '{action}'。支持的操作只有: list, add, delete, update。", "参数错误")

        if action == "list":
            # list 操作：不需要额外参数
            try:
                crons = list_crons()
                snip = f"共 {len(crons)} 个闹钟"
                return text_response(crons, snip)
            except CronError as e:
                return error_response(str(e), "查询失败")
        
        elif action == "add":
            if not name or not str(name).strip():
                return error_response("add（添加）操作失败。引导：缺少必需参数 'name'，请提供闹钟的名称/标题（如 name='早会'）。", "参数缺失")

            if not trigger_time or not str(trigger_time).strip():
                return error_response("add（添加）操作失败。引导：缺少必需参数 'trigger_time'，请提供 24 小时制的时间，格式为 HH:MM（如 trigger_time='08:30'）。", "参数缺失")

            if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", str(trigger_time).strip()):
                return error_response(f"时间格式错误：'{trigger_time}'。引导：必须严格使用 HH:MM 格式，例如 09:00 或 14:30。", "参数格式错误")

            actual_rule = repeat_rule if repeat_rule else "none"
            try:
                result = add_cron(title=name, trigger_time=trigger_time, repeat_rule=actual_rule)
                return text_response(result, f"添加成功: {result['title']} ({result['trigger_time']})")
            except CronError as e:
                return warning_response(str(e), "添加失败")
        
        elif action == "delete":
            if not name or not str(name).strip():
                return error_response("delete（删除）操作失败。引导：缺少必需参数 'name'，请提供要删除的闹钟名称或完整 ID。", "参数缺失")

            try:
                result = delete_cron(identifier=name)
                return text_response(result, result["message"])
            except CronError as e:
                return warning_response(f"删除失败。原因：{str(e)}。引导：请确认填入的 name 或 ID 是否正确（可通过 action='list' 查询当前闹钟）。", "删除失败")
        
        elif action == "update":
            if not name or not str(name).strip():
                return error_response("update（修改）操作失败。引导：缺少必需参数 'name' 作为查找凭据，请提供要修改的闹钟名称或完整 ID。", "参数缺失")

            if trigger_time is None and repeat_rule is None and active is None:
                return error_response("update（修改）操作缺少修改内容。引导：请至少提供 'trigger_time'、'repeat_rule' 或 'active' 中的一个字段以进行更新（注：名称不支持修改）。", "参数缺失")

            if trigger_time and not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", str(trigger_time).strip()):
                return error_response(f"时间格式错误：'{trigger_time}'。引导：修改的时间必须严格使用 HH:MM 格式。", "参数格式错误")

            try:
                result = update_cron(
                    identifier=name,
                    trigger_time=trigger_time,
                    repeat_rule=repeat_rule,
                    active=active
                )
                return text_response(result, result["message"])
            except CronError as e:
                return warning_response(f"修改失败。原因：{str(e)}。引导：请确认闹钟名称或 ID 是否正确，或时间/规则格式是否合法。", "修改失败")
        
        return error_response("未知错误", "系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"Cron 运行时异常: {str(e)}。引导：可能是文件读写错误或内部逻辑异常。", "执行失败")