"""工具输出超长时的落盘与预览封装。"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from src.tool.utils.token_limit import count_tokens, truncate_to_tokens


def safe_truncate(data: Any, max_tokens: int) -> str:
    """结构化安全省略策略：按 token 预算截断预览"""
    data_str = (
        json.dumps(data, ensure_ascii=False, indent=2)
        if isinstance(data, (dict, list))
        else str(data)
    )

    if count_tokens(data_str) <= max_tokens:
        return data_str

    preview = truncate_to_tokens(data_str, max_tokens)
    omitted_chars = len(data_str) - len(preview)
    return f"{preview}\n\n... [后续约 {omitted_chars} 字符已被截断，请使用 Bash 工具读取落盘的缓存文件] ..."


def write_overflow_cache(content: str, tool_name: str, buffer_dir: str) -> str:
    """把完整输出写入 .buffer/<tool>/，返回纯文件名。"""
    tool_dir = os.path.join(buffer_dir, tool_name)
    os.makedirs(tool_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    file_name = f"{timestamp}_{uuid.uuid4().hex[:4]}.txt"
    with open(os.path.join(tool_dir, file_name), "w", encoding="utf-8") as f:
        f.write(content)
    return file_name


def overflow_prompt(
    *,
    tool_name: str,
    content_token_count: int,
    max_output_tokens: int,
    file_name: str,
    preview: str,
) -> str:
    """超长输出的模型可读提示（含落盘路径与预览）。"""
    return (
        f"⚠️ [系统拦截] {tool_name} 输出总长约 {content_token_count} token，超出当前安全余量阈值（{max_output_tokens} token）。完整结果已落盘：\n"
        f"🐳 沙盒内路径: /agent_vm/.buffer/{tool_name}/{file_name}\n"
        f"如果你需要查看剩余的内容，请务必使用 Bash (cat/grep/sed/tail) 工具去上述缓存文件里分批阅读！\n"
        f"\n--- 内容预览 (前 {max_output_tokens} token) ---\n"
        f"{preview}"
    )
