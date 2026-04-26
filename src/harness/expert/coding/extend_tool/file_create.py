"""
file_create — 创建新文件工具

支持：
- 创建新文件并写入内容
- 自动创建父目录（不存在时）
- 可选覆盖已存在文件（需显式确认）
"""

import json
import os
from .path_utils import validate_path, resolve_project_root, ensure_parent_dir


FILE_CREATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "file_create",
        "description": "创建新文件并写入内容。如果父目录不存在会自动创建。默认不会覆盖已有文件，需显式设置 overwrite=true。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要创建的文件绝对路径"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "如果文件已存在，是否覆盖（默认 false）"
                }
            },
            "required": ["file_path", "content"]
        }
    }
}


def execute_file_create(arguments: dict, task=None) -> str:
    file_path = arguments.get("file_path", "")
    content = arguments.get("content", "")
    overwrite = arguments.get("overwrite", False)

    if not file_path:
        return json.dumps({"type": "error", "content": "❌ file_path 不能为空"})

    # ── 路径安全校验 ──
    try:
        project_root = resolve_project_root(task)
        file_path = validate_path(file_path, project_root)
    except ValueError as e:
        return json.dumps({"type": "error", "content": str(e)})

    # ── 检查文件是否已存在 ──
    if os.path.exists(file_path):
        if not overwrite:
            return json.dumps({
                "type": "error",
                "content": (
                    f"❌ 文件已存在: {file_path}\n"
                    f"💡 如需覆盖，请设置 overwrite=true"
                )
            })
        if not os.path.isfile(file_path):
            return json.dumps({
                "type": "error",
                "content": f"❌ 路径已存在但不是文件: {file_path}"
            })

    # ── 自动创建父目录 ──
    ensure_parent_dir(file_path)

    # ── 写入文件 ──
    try:
        mode = "w" if overwrite else "x"
        # 如果文件不存在但 overwrite 是 false，用 x 模式（排他创建）
        # 如果 overwrite 是 true，用 w 模式
        if overwrite:
            mode = "w"
        else:
            mode = "x"
        
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(content)
        
        # 统计行数
        line_count = content.count("\n")
        if content and not content.endswith("\n"):
            line_count += 1
        
        char_count = len(content)
        created = "覆盖" if overwrite and os.path.exists(file_path) else "创建"
        
        return json.dumps({
            "type": "text",
            "content": (
                f"✅ 文件{created}成功: `{file_path}`\n"
                f"   行数: {line_count}, 字符数: {char_count}"
            )
        }, ensure_ascii=False)
        
    except FileExistsError:
        return json.dumps({
            "type": "error",
            "content": (
                f"❌ 文件已存在: {file_path}\n"
                f"💡 如需覆盖，请设置 overwrite=true"
            )
        })
    except Exception as e:
        return json.dumps({
            "type": "error",
            "content": f"❌ 写入文件失败: {e}"
        })
