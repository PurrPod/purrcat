"""Bash 工具模块 - 严格遵循 plugins/route/base_tool.py 原代码逻辑"""

from src.tool.utils.format import text_response, warning_response
from .docker_env import get_docker_manager


def Bash(command: str, timeout: int = 300) -> str:
    """
    在安全的沙盒环境 (Docker) 中执行 Shell 命令。
    
    此函数严格遵循原代码 execute_command 的逻辑，参数只保留 command 和 timeout，
    内部强制使用 session_id="default" 保护会话状态。
    
    Args:
        command: 要执行的 Shell 命令（支持连串命令和多行文本，请注意正确的引号转义）
        timeout: 命令执行的超时时间（秒），默认 300 秒
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip 字段
    """
    session_id = "default"
    manager = get_docker_manager()
    exit_code, output, cwd = manager.execute(session_id, command, timeout)
    
    result = {
        "session_id": session_id,
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


def close_session(session_id: str = "default") -> str:
    """
    关闭 Shell 会话
    
    Args:
        session_id: 会话 ID，默认 "default"
    
    Returns:
        格式化后的 JSON 字符串
    """
    get_docker_manager().close_shell(session_id)
    content = f"Shell session '{session_id}' successfully closed."
    return text_response(content, f"关闭会话: {session_id}")