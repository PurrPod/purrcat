"""Cron 工具主入口 - 统一调度 list、add、delete、update 操作"""

import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.cron.exceptions import (
    CronError,
    InvalidActionError,
    MissingParameterError,
    InvalidParameterError
)
from src.tool.cron.cron_operations import (
    add_cron,
    delete_cron,
    update_cron,
    list_crons
)


def Cron(action: str, name: str = None, trigger_time: str = None, 
         repeat_rule: str = "none", active: bool = None, **kwargs) -> str:
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
        # 参数校验
        action = action.strip().lower() if action else ""
        
        # 检查操作类型
        if action not in ["list", "add", "delete", "update"]:
            return error_response(
                f"无效的操作类型: {action}。支持的操作: list, add, delete, update", 
                "参数错误"
            )
        
        # 根据操作类型执行相应逻辑
        if action == "list":
            # list 操作：不需要额外参数
            try:
                crons = list_crons()
                snip = f"共 {len(crons)} 个闹钟"
                return text_response(crons, snip)
            except CronError as e:
                return error_response(str(e), "查询失败")
        
        elif action == "add":
            # add 操作：需要 name 和 trigger_time
            if not name or not name.strip():
                return error_response("add 操作需要提供 name（闹钟名称）", "参数错误")
            
            if not trigger_time or not trigger_time.strip():
                return error_response("add 操作需要提供 trigger_time（触发时间，HH:MM 格式）", "参数错误")
            
            try:
                result = add_cron(title=name, trigger_time=trigger_time, repeat_rule=repeat_rule)
                snip = f"添加成功: {result['title']} ({result['trigger_time']})"
                return text_response(result, snip)
            except CronError as e:
                return warning_response(str(e), "添加失败")
        
        elif action == "delete":
            # delete 操作：需要 name（作为 cron_id）
            if not name or not name.strip():
                return error_response("delete 操作需要提供 name（闹钟 ID）", "参数错误")
            
            try:
                result = delete_cron(cron_id=name)
                snip = f"删除成功: {name}"
                return text_response(result, snip)
            except CronError as e:
                return warning_response(str(e), "删除失败")
        
        elif action == "update":
            # update 操作：需要 name（作为 cron_id），其他参数可选
            if not name or not name.strip():
                return error_response("update 操作需要提供 name（闹钟 ID）", "参数错误")
            
            try:
                result = update_cron(
                    cron_id=name,
                    title=kwargs.get('title') or name,  # 如果没有单独传 title，使用 name
                    trigger_time=trigger_time,
                    repeat_rule=repeat_rule,
                    active=active
                )
                snip = f"修改成功: {name}"
                return text_response(result, snip)
            except CronError as e:
                return warning_response(str(e), "修改失败")
        
        return error_response("未知错误", "系统错误")
        
    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"Cron 运行时异常: {str(e)}", "执行失败")