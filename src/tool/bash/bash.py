"""Bash 工具模块 - 严格遵循 plugins/route/base_tool.py 原代码逻辑"""

import traceback

from src.tool.utils.format import error_response, text_response, warning_response

from .docker_env import get_docker_manager
from .exceptions import (
    BashTimeoutError,
    DockerImageNotFoundError,
    DockerNotRunningError,
)


def Bash(command: str, timeout: int = 300, session_id: str = "default", **kwarg) -> str:
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
            return error_response(
                "Bash command 不能为空，请提供要执行的 Shell 指令。", "❌ 参数错误"
            )

        # 使用系统注入的 session_id（agent/task 层注入），默认 "default"
        manager = get_docker_manager()
        exit_code, output, cwd = manager.execute(session_id, command, timeout)

        content_str = (
            f"执行目录: {cwd}\n"
            f"退出代码: {exit_code}\n"
            f"输出:\n{output if output else '[无输出]'}"
        )

        if exit_code == 0:
            snip = "✅ 成功"
            return text_response(content_str, snip)
        else:
            close_session(session_id)
            snip = f"❌ 失败(exit={exit_code})"
            return warning_response(content_str, snip)

    except DockerNotRunningError:
        # 处理 Docker 未启动/连接异常
        return error_response(
            "Docker未连接，可能是老板没有开启Docker Desktop，请通知老板检查Docker状态",
            "❌ 环境异常",
        )

    except DockerImageNotFoundError:
        # 处理镜像缺失/构建启动异常
        return error_response(
            "Docker启动或构建容器异常，请提醒老板进行相关操作", "❌ 环境异常"
        )

    except BashTimeoutError:
        # 处理 Bash 执行超时异常
        return error_response(
            "执行超时（超过300秒）。如果该操作涉及网络下载（如 pip install、apt-get 等），由于沙盒网络与宿主机不同步，极易因为网络阻塞导致卡死。请优先考虑在命令中临时换源（例如使用 pip install 包名 -i https://pypi.tuna.tsinghua.edu.cn/simple）并重试。",
            "❌ 执行超时(建议换源)",
        )

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
