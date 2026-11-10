"""Port selection shared by the Python API entry point and its tests."""

from __future__ import annotations

import json
import os
import socket

from src.utils._fs import write_json_atomic

DEFAULT_API_PORT = 8000
DEFAULT_SCAN_ATTEMPTS = 50

# 🌟 运行时端口状态：由真正 bind 成功的后端进程写、外部消费者读。
# 端口 fallback 后（8000 被占 → 8001），settings.json 里的 acp_port 仍是旧的期望值，
# ACP relay / 配置面板若各自读配置就会指向错误端口；统一读这里保证只有一个事实来源。
RUNTIME_STATE_FILENAME = "runtime.json"


def parse_port(value: object | None) -> int | None:
    """Parse a configured port, returning ``None`` when it is not configured."""

    if value is None or str(value).strip() == "":
        return None

    raw = str(value).strip()
    if not raw.isdecimal():
        raise ValueError(
            f'Invalid API port "{value}". Use an integer between 1 and 65535.'
        )

    port = int(raw)
    if not 1 <= port <= 65535:
        raise ValueError(
            f'Invalid API port "{value}". Use an integer between 1 and 65535.'
        )
    return port


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Return whether the API can bind ``host:port`` at this moment."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def resolve_api_port(
    requested: object | None,
    *,
    host: str = "0.0.0.0",
    start: int = DEFAULT_API_PORT,
    attempts: int = DEFAULT_SCAN_ATTEMPTS,
) -> int:
    """Resolve an explicit port or the first available port from the default range.

    An explicit port is strict: it never silently falls back. With no explicit
    value, the default port is tried first and then subsequent ports are used.
    """

    explicit = requested is not None and str(requested).strip() != ""
    if explicit:
        port = parse_port(requested)
        assert port is not None
        if not is_port_available(port, host):
            raise ValueError(f"API port {port} is unavailable.")
        return port

    if not 1 <= start <= 65535:
        raise ValueError("API port scan start must be between 1 and 65535.")
    if attempts < 1:
        raise ValueError("API port scan attempts must be a positive integer.")

    for offset in range(attempts):
        port = start + offset
        if port > 65535:
            break
        if is_port_available(port, host):
            return port

    end = min(65535, start + attempts - 1)
    raise ValueError(f"No available API port found between {start} and {end}.")


def runtime_state_path() -> str:
    """运行时端口状态文件路径。

    这里延迟导入配置模块：main.py 在配置初始化之前就 import 本模块，
    过早把配置模块拉进导入链会让它的模块级路径计算提前跑（首启模板配置踩过坑）。
    """

    from src.utils.config import PURRCAT_DIR

    return os.path.join(PURRCAT_DIR, RUNTIME_STATE_FILENAME)


def runtime_state_port(state: object) -> int | None:
    """从运行时状态里取可用端口。

    非 1..65535 的整数一律拒绝：bool 是 int 子类必须显式排除；文件可能被外部工具
    或手改成浮点、越界值，这些视为无效让调用方回落。数字字符串按 parse_port 的
    口径接受，与「配置端口」的容忍度保持一致。
    """

    if not isinstance(state, dict):
        return None
    value = state.get("api_port")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return parse_port(value)
    except ValueError:
        return None


def write_runtime_state(port: object, path: str | None = None) -> bool:
    """记录本进程实际服务的端口。

    走「临时文件 + os.replace」原子替换，读取方永远看不到写一半的内容；
    失败只返回 False，绝不抛出。被强杀残留的旧文件无害：下次启动会覆盖它，
    值不可用时读取方也会回落。
    """

    try:
        parsed = parse_port(port)
    except ValueError:
        return False
    if parsed is None:
        return False

    target = path or runtime_state_path()
    payload = {"api_port": parsed, "pid": os.getpid()}
    try:
        write_json_atomic(target, payload, indent=None)
    except Exception:
        return False
    return True


def read_runtime_port(path: str | None = None) -> int | None:
    """读取实际端口；文件缺失、损坏或值非法时一律返回 None，绝不抛出。"""

    try:
        with open(path or runtime_state_path(), "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except Exception:
        return None
    return runtime_state_port(state)


def clear_runtime_state(path: str | None = None) -> None:
    """正常退出时删除运行时状态文件；尽力而为，不抛出。"""

    try:
        os.unlink(path or runtime_state_path())
    except OSError:
        pass
