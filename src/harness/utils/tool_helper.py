"""
工具执行辅助函数：将工具解析和执行逻辑提取为纯函数，便于多个节点复用

核心设计原则：
1. 纯函数：不依赖外部状态，输入确定则输出确定
2. 无副作用：不修改传入参数
3. 可测试：易于单元测试
"""
import json
import datetime
from typing import Any, List, Dict
from json_repair import repair_json
from harness.tools.base_tool import BaseToolDispatcher


def extract_tool_calling(response) -> list:
    """
    从 LLM 响应中提取工具调用信息
    
    Args:
        response: LLM 响应对象
        
    Returns:
        工具调用列表
    """
    if hasattr(response, 'choices') and len(response.choices) > 0:
        return getattr(response.choices[0].message, "tool_calls", []) or []
    return []


def parse_tool_arguments(arguments_str: str) -> dict:
    """
    解析工具参数，支持 JSON 修复
    
    Args:
        arguments_str: 参数字符串
        
    Returns:
        解析后的参数字典
    """
    if not arguments_str:
        return {}
    
    try:
        return json.loads(arguments_str)
    except json.JSONDecodeError:
        try:
            return repair_json(arguments_str, return_objects=True)
        except Exception:
            return {}


def check_tool_call_completed(tool_calls: list, tool_name: str = "task_done") -> bool:
    """
    检查是否调用了指定工具（默认检查 task_done）
    
    Args:
        tool_calls: 工具调用列表
        tool_name: 要检查的工具名
        
    Returns:
        是否调用了指定工具
    """
    return any(tc.function.name == tool_name for tc in tool_calls)


def execute_tool_call(tool_calls: list, context: Any, node_log_func) -> List[dict]:
    """
    执行工具调用并返回结果消息列表
    
    Args:
        tool_calls: 工具调用列表
        context: 上下文对象
        node_log_func: 日志记录函数
        
    Returns:
        工具执行结果消息列表
    """
    tool_messages = []
    
    for tc in tool_calls:
        original_tool_name = tc.function.name
        arguments_str = tc.function.arguments
        arguments = parse_tool_arguments(arguments_str)
        
        if not isinstance(arguments, dict):
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": original_tool_name,
                "content": "❌ 系统拦截：工具参数格式严重损坏，请检查 JSON 格式！"
            })
            continue
        
        args_str = ", ".join([f"{k}={repr(v)}" for k, v in arguments.items()])
        node_log_func(context, "TOOL_CALL", f"🔧 助手调起工具: {original_tool_name}({args_str})", {"arguments": arguments})
        
        try:
            result_str = BaseToolDispatcher.dispatch(original_tool_name, arguments, context=context)
        except Exception as e:
            result_str = json.dumps({"error": str(e)}, ensure_ascii=False)
        
        node_log_func(context, "TOOL", f"📦 工具回传结果: {result_str}")
        
        finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            parsed_res = json.loads(result_str)
            if isinstance(parsed_res, dict):
                parsed_res["timestamp"] = finish_time
                final_content = json.dumps(parsed_res, ensure_ascii=False)
            else:
                final_content = json.dumps({"content": parsed_res, "timestamp": finish_time}, ensure_ascii=False)
        except json.JSONDecodeError:
            final_content = json.dumps({"content": result_str, "timestamp": finish_time}, ensure_ascii=False)
        
        tool_messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "name": original_tool_name,
            "content": final_content
        })
    
    return tool_messages
