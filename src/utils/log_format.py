"""任务日志的纯渲染逻辑（不触碰文件系统）。"""

import json
import re

from rich.markup import escape

from src.utils._format import format_hms

_PREFIXES_TO_STRIP = [
    "🔧 助手调起工具: ",
    "📦 工具回传结果: ",
    "🤖 助手思考: ",
    "📋 ",
]

_COLOR_MAP = {
    "system": "#9399b2",
    "thought": "#88c0d0",
    "tool_call": "#ebcb8b",
    "tool": "#a3be8c",
    "warning": "#d08770",
    "error": "#bf616a",
    "plan": "#81a1c1",
}

_EMOJI_MAP = {
    "system": "⚙️",
    "thought": "🤖",
    "tool_call": "🔧",
    "tool": "📦",
    "warning": "⚠️",
    "error": "❌",
    "plan": "📋",
}


def clean_log_entry(entry: dict) -> str:
    card_type = entry.get("card_type", "unknown")
    content = str(entry.get("content", ""))
    metadata = entry.get("metadata", {})

    if card_type == "tool_call":
        args = metadata.get("arguments", {})
        if "command" in args:
            cmd = args["command"]
            m = re.search(r"cat\s+>\s+([^\s]+)\s+<<\s*'PYEOF'", cmd)
            if m:
                file_name = m.group(1).split("/")[-1]
                return f"execute_command ➔ 写入文件: {file_name} (长代码已折叠)"

            clean_cmd = cmd.replace("\n", " ")
            if len(clean_cmd) > 80:
                return f"execute_command ➔ {clean_cmd[:80]}..."
            return f"execute_command ➔ {clean_cmd}"

        elif args:
            args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
            tool_name = content.split("(")[0].replace("🔧 助手调起工具: ", "").strip()
            return f"{tool_name}({args_str})"

    elif card_type == "tool":
        try:
            json_start = content.find("{")
            if json_start != -1:
                res = json.loads(content[json_start:])
                if res.get("type") == "text":
                    inner_content = res.get("content", {})
                    exit_code = inner_content.get("exit_code")
                    output = inner_content.get("output", "").strip()

                    if exit_code == 0:
                        out_msg = (
                            f", 输出: {output[:30]}..." if output else ", 无标准输出"
                        )
                        return f"✅ 执行成功 (exit_code: 0{out_msg})"
                    else:
                        return f"❌ 执行失败 (exit_code: {exit_code}, 报错: {output[:50]}...)"
        except Exception:
            pass

    for prefix in _PREFIXES_TO_STRIP:
        content = content.replace(prefix, "")

    return content.strip()


def render_log_entry(entry: dict) -> str:
    """把一条日志记录渲染成 rich markup 单行。"""
    card_type = entry.get("card_type", "unknown")
    time_str = format_hms(entry.get("timestamp", 0))
    content = escape(clean_log_entry(entry))
    color = _COLOR_MAP.get(card_type, "white")
    emoji = _EMOJI_MAP.get(card_type, "📄")
    label = card_type.upper().ljust(9)
    return f"[dim][{time_str}][/dim] [{color}]{emoji} {label}[/{color}] │ {content}"
