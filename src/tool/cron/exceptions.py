"""Cron 工具异常类"""


class CronError(Exception):
    """Cron 操作基类异常"""
    pass


class InvalidActionError(CronError):
    """无效的操作类型"""
    def __init__(self, action: str):
        super().__init__(f"无效的操作类型: {action}。支持的操作: list, add, delete, update")


class MissingParameterError(CronError):
    """缺少必需参数"""
    def __init__(self, param_name: str, action: str = None):
        action_text = f"（操作: {action}）" if action else ""
        super().__init__(f"缺少必需参数: {param_name}{action_text}")


class InvalidParameterError(CronError):
    """参数无效"""
    def __init__(self, param_name: str, reason: str):
        super().__init__(f"参数 '{param_name}' 无效: {reason}")


class CronNotFoundError(CronError):
    """闹钟不存在"""
    def __init__(self, cron_id: str):
        super().__init__(f"找不到闹钟 ID: {cron_id}")


class InvalidTimeFormatError(CronError):
    """时间格式无效"""
    def __init__(self, time_str: str):
        super().__init__(f"无效的时间格式: {time_str}。请使用 HH:MM 格式（如 08:30）")


class InvalidRepeatRuleError(CronError):
    """重复规则无效"""
    def __init__(self, rule: str):
        valid_rules = ["none", "everyday", "weekly_1", "weekly_2", "weekly_3", 
                       "weekly_4", "weekly_5", "weekly_6", "weekly_7"]
        super().__init__(f"无效的重复规则: {rule}。支持的规则: {', '.join(valid_rules)}")