"""
file_read — 智能文件读取工具

借鉴 Claude Code FileReadTool 设计：
- 支持指定行范围读取，避免大文件全量加载
- 显示行号
- 支持上下文扩展（center + window 模式）
- 文件元信息（大小、行数、修改时间）
"""

import json
import os
import datetime
from .path_utils import validate_path, resolve_project_root, ensure_parent_dir

FILE_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "file_read",
        "description": "读取文件内容，支持指定行范围、显示行号、上下文扩展。大文件自动分页读取，避免撑爆上下文。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件绝对路径"
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），默认 1"
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号，默认读到文件末尾"
                },
                "max_lines": {
                    "type": "integer",
                    "description": "最多读取行数，默认 200，防止超长文件撑爆上下文"
                },
                "show_line_numbers": {
                    "type": "boolean",
                    "description": "是否显示行号，默认 true"
                }
            },
            "required": ["file_path"]
        }
    }
}


def _format_size(size: int) -> str:
    if size > 1024 * 1024:
        return f"{size / 1024 / 1024:.1f}MB"
    elif size > 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size}B"


def execute_file_read(arguments: dict, task=None) -> str:
    file_path = arguments.get("file_path", "")
    start_line = arguments.get("start_line", 1)
    end_line = arguments.get("end_line")
    max_lines = arguments.get("max_lines", 200)
    show_line_numbers = arguments.get("show_line_numbers", True)

    if not file_path:
        return json.dumps({"type": "error", "content": "❌ file_path 不能为空"})

    # ── 路径安全校验 ──
    try:
        project_root = resolve_project_root(task)
        file_path = validate_path(file_path, project_root)
    except ValueError as e:
        return json.dumps({"type": "error", "content": str(e)})

    if not os.path.isfile(file_path):
        hint = ""
        if file_path.startswith("/agent_vm/"):
            hint = "\n💡 检测到沙盒路径 /agent_vm/...，当前操作在宿主机文件系统上。请确认路径是否正确。"
        return json.dumps({
            "type": "error",
            "content": (
                f"❌ 文件不存在: {file_path}"
                f"{hint}"
            )
        })

    try:
        # ── 文件元信息 ──
        stat = os.stat(file_path)
        file_size = stat.st_size
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        # ── 大文件保护 ──
        if file_size > 10 * 1024 * 1024:  # 10MB
            return json.dumps({
                "type": "text",
                "content": f"⚠️ 文件过大 ({_format_size(file_size)})，跳过读取。请缩小范围或使用 code_search grep 搜索。"
            })

        # ── 读取文件 ──
        with open(file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # ── 校验行范围 ──
        if start_line < 1:
            start_line = 1
        if end_line is None or end_line > total_lines:
            end_line = total_lines

        # ── 限制最大读取行数 ──
        if end_line - start_line + 1 > max_lines:
            original_end = end_line
            end_line = start_line + max_lines - 1
            truncated = True
        else:
            truncated = False

        # ── 提取内容 ──
        selected = all_lines[start_line - 1:end_line]
        line_num_width = len(str(end_line))

        # ── 构建输出 ──
        header = f"📄 `{os.path.relpath(file_path) if os.path.exists(file_path) else file_path}`"
        header += f" ({_format_size(file_size)}, {total_lines} 行, 修改于 {mtime})"

        if show_line_numbers:
            content_lines = []
            for i, line in enumerate(selected, start=start_line):
                line_num = str(i).rjust(line_num_width)
                content_lines.append(f"  {line_num} | {line.rstrip()}")
            content = "\n".join(content_lines)
        else:
            content = "".join(selected).rstrip()

        result = header + "\n\n"
        if truncated:
            result += f"⚠️ 仅显示 {start_line}-{end_line} 行（原范围 {start_line}-{original_end}，共 {total_lines} 行），共 {len(selected)} 行\n\n"
        result += content

        return json.dumps({"type": "text", "content": result}, ensure_ascii=False)

    except UnicodeDecodeError:
        return json.dumps({
            "type": "text",
            "content": f"⚠️ 文件 {file_path} 不是文本文件（无法以 UTF-8 解码），请确认文件类型。"
        })
    except Exception as e:
        return json.dumps({"type": "error", "content": f"❌ 读取文件失败: {e}"})
