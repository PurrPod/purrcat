"""Config API 的可纯化校验（SPEC-020）。

只放不依赖进程/网络/Agent 的校验与解析：ACP 端口、数据根路径、
Markdown 文件名白名单、JSON 读取与 sandbox registry 归一化。
"""

import json
import os
from typing import Any

from fastapi import HTTPException

MARKDOWN_FILENAMES = ("SOUL", "GOAL")


def validate_acp_port(port) -> int:
    """ACP 端口必须是 1-65536 的整数，否则 400。"""
    if not isinstance(port, int) or not (0 < port < 65536):
        raise HTTPException(status_code=400, detail="端口必须是 1-65536 的整数")
    return port


def validate_data_root(value: str) -> str:
    """校验数据根目录候选路径，非法直接抛 HTTPException"""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail="数据目录不能为空")
    value = value.strip()

    if not os.path.isabs(value):
        raise HTTPException(
            status_code=400, detail="数据目录必须是绝对路径，如 D:\\purrcat_data"
        )

    # 拒绝磁盘根目录，避免 agent_vm 等直接散落在盘符根下
    drive, _ = os.path.splitdrive(value)
    if drive and os.path.normpath(value) == os.path.normpath(drive + os.sep):
        raise HTTPException(
            status_code=400, detail="不能直接选择磁盘根目录，请选择盘下的一个子目录"
        )
    return os.path.normpath(value)


def validate_markdown_filename(filename: str) -> str:
    """只允许 SOUL / GOAL，防止任意路径穿越。"""
    if filename not in MARKDOWN_FILENAMES:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


def load_json_data(path: str, default: Any, log_prefix: str = "[Config API]") -> Any:
    """读取 JSON；缺失或损坏时返回 default，并按需记录日志。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        if log_prefix:
            print(f"{log_prefix} 读取 {os.path.basename(path)} 失败: {e}")
        return default


def normalize_sandbox_registry(value: Any) -> str:
    """registry 前缀去空白与末尾斜杠；留空表示自动依次尝试官方与公共源。"""
    return str(value or "").strip().rstrip("/")
