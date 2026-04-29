"""Bash 工具模块 - 严格遵循 plugins/route/base_tool.py 原代码逻辑"""

import traceback
from src.tool.utils.format import text_response, warning_response, error_response
from .docker_env import get_docker_manager


def Bash(command: str, timeout: int = 300, session_id: str = "default") -> str:
    """
    在安全的沙盒环境 (Docker) 中执行 Shell 命令。
    
    Args:
        command: 要执行的 Shell 命令（支持连串命令和多行文本，请注意正确的引号转义）
        timeout: 命令执行的超时时间（秒），默认 300 秒
        session_id: 会话 ID（由系统注入，模型无需关注）
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip 字段
    """
    try:
        # 命令判空校验
        if not command or not command.strip():
            return error_response("Bash command 不能为空，请提供要执行的 Shell 指令。", "参数错误")
        
        # 使用系统注入的 session_id（agent/task 层注入），默认 "default"
        manager = get_docker_manager()
        exit_code, output, cwd = manager.execute(session_id, command, timeout)
        
        result = {
            "exit_code": exit_code,
            "output": output,
            "cwd": cwd
        }
        
        # 生成 snip 摘要：简短描述执行结果
        if exit_code == 0:
            output_str = str(output) if output else ""
            snip = f"成功 (exit_code=0): {output_str[:50]}..." if len(output_str) > 50 else "成功 (exit_code=0)"
            return text_response(result, snip)
        else:
            snip = f"失败 (exit_code={exit_code})"
            return warning_response(result, snip)
            
    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"Docker/Shell 运行时异常: {str(e)}", "执行失败")


def close_session(session_id: str = "default") -> str:
    """
    关闭 Shell 会话
    
    Args:
        session_id: 会话 ID，默认 "default"
    
    Returns:
        格式化后的 JSON 字符串
    """
    try:
        get_docker_manager().close_shell(session_id)
        content = f"Shell session '{session_id}' successfully closed."
        return text_response(content, f"关闭会话: {session_id}")
    except Exception as e:
        traceback.print_exc()
        return error_response(f"关闭会话失败: {str(e)}", "操作失败")