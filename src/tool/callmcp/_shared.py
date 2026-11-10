"""MCP 网关的共享纯函数：配置指纹、环境净化和媒体载荷解析。"""

from __future__ import annotations

import base64
import hashlib
import json

# 父进程（桌面壳 venv）透传的变量会冲掉 uv-managed CPython 的库路径
PARENT_PYTHON_ENV = (
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)


def config_fingerprint(config: dict) -> str:
    """command/args/env 任一变化即需要重启子进程。"""
    env = config.get("env")
    material = {
        "command": config.get("command", ""),
        "args": config.get("args", []),
        "env": env if isinstance(env, dict) else {},
    }
    raw = json.dumps(material, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_safe_env(custom_env: dict | None, base_env: dict) -> dict:
    """合并自定义环境变量：跳过 None、值转字符串、剥离父进程 Python 变量。"""
    env = dict(base_env)
    for key, value in (custom_env or {}).items():
        if value is not None:
            env[key] = str(value)

    for key in PARENT_PYTHON_ENV:
        env.pop(key, None)

    return env


def decode_image_content(content) -> tuple[bytes, str]:
    """解析 MCP 图片内容：剥离 data URL 前缀，jpeg 扩展名归一化为 jpg。"""
    mime_type = getattr(content, "mimeType", "image/png")
    payload = content.data
    if "," in payload and payload.startswith("data:"):
        payload = payload.split(",", 1)[1]

    ext = mime_type.split("/")[-1] if "/" in mime_type else "png"
    if ext == "jpeg":
        ext = "jpg"

    return base64.b64decode(payload), ext
