import json
import time


def format_tool_response(msg_type: str, content: str | dict, snip: str = "") -> str:
    """
    统一的工具返回格式处理函数
    
    Args:
        msg_type: 消息类型，如 'text', 'warning', 'error'
        content: 工具返回的内容，可以是字符串或字典
        snip: 内容摘要（可选），由工具提供
    
    Returns:
        格式化后的JSON字符串，包含 timestamp, type, content, snip 四个字段
    """
    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": msg_type,
        "content": content,
        "snip": snip
    }
    return json.dumps(result, ensure_ascii=False)


def text_response(content: str | dict, snip: str = "") -> str:
    """快捷函数：返回文本类型响应"""
    return format_tool_response("text", content, snip)


def warning_response(content: str | dict, snip: str = "") -> str:
    """快捷函数：返回警告类型响应"""
    return format_tool_response("warning", content, snip)


def error_response(content: str | dict, snip: str = "") -> str:
    """快捷函数：返回错误类型响应"""
    return format_tool_response("error", content, snip)