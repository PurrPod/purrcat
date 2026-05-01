"""Bash 工具模块 - 严格遵循 plugins/route/base_tool.py 原代码逻辑"""

import traceback
from src.tool.utils.format import text_response, warning_response, error_response
from .docker_env import get_docker_manager
from .exceptions import DockerNotRunningError, DockerImageNotFoundError, BashTimeoutError


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
            return error_response("Bash command 不能为空，请提供要执行的 Shell 指令。", "❌ 参数错误")
        
        # 使用系统注入的 session_id（agent/task 层注入），默认 "default"
        manager = get_docker_manager()
        exit_code, output, cwd = manager.execute(session_id, command, timeout)
        
        result = {
            "exit_code": exit_code,
            "output": output,
            "cwd": cwd
        }
        
        # 生成 snip 摘要：简短描述执行结果
        output_preview = output[:40].replace('\n', ' ') if output else ''
        if exit_code == 0:
            snip = f"✅ 成功 | {output_preview}..."
            return text_response(result, snip)
        else:
            snip = f"❌ 失败(exit={exit_code}) | {output_preview}..."
            return warning_response(result, snip)
            
    except DockerNotRunningError:
        # 处理 Docker 未启动/连接异常
        return error_response("Docker未连接，可能是老板没有开启Docker Desktop，请通知老板检查Docker状态", "❌ 环境异常")
        
    except DockerImageNotFoundError:
        # 处理镜像缺失/构建启动异常
        return error_response("Docker启动或构建容器异常，请提醒老板进行相关操作", "❌ 环境异常")
        
    except BashTimeoutError:
        # 处理 Bash 执行超时异常
        return error_response("执行超时，如果是有关下载操作，可能由于网络原因，如是请联系老板进行沙盒的网络配置或检查宿主机网络状态", "❌ 执行超时")
        
    except Exception as e:
        # 兜底捕获其他未知的运行时异常
        traceback.print_exc()
        return error_response(f"Docker/Shell 运行时异常: {str(e)}", "❌ 执行失败")


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