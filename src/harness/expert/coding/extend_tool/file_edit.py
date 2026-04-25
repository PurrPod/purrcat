"""
file_edit — search/replace 精确文件编辑工具

借鉴 Claude Code FileEditTool 的设计理念：
- 基于 old_string → new_string 的精准替换，而非整文件覆写
- 自动备份原始文件（.bak.时间戳）
- 多行匹配支持，精确查找定位
- 生成 diff 预览变更
- 可选的 replace_all 模式

安全机制：
  1. old_string 必须在文件中唯一匹配（replace_all 时除外）
  2. 编辑前自动备份
  3. 旧/新字符串必须不同
"""

import json
import os
import difflib
import shutil
import datetime
from .path_utils import validate_path, resolve_project_root

FILE_EDIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "file_edit",
        "description": "对文件进行 search/replace 精确编辑。指定要查找的文本和替换文本，精准定位修改。支持多行匹配和自动备份。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要修改的文件绝对路径"
                },
                "old_string": {
                    "type": "string",
                    "description": "被替换的原始文本（必须与文件中内容精确匹配）"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新文本（必须与 old_string 不同）"
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "是否替换所有匹配项（默认 false，只替换第一个）"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "仅预览 diff，不实际修改文件"
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }
    }
}


def _normalize_line_endings(text: str) -> str:
    """统一换行符为 \\n"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _generate_diff(file_path: str, old_content: str, new_content: str) -> str:
    """生成 unified diff"""
    rel_path = os.path.basename(file_path)
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
    )
    return "".join(diff)


def _find_all_occurrences(content: str, old_string: str) -> list[int]:
    """返回所有匹配的起始位置"""
    positions = []
    start = 0
    while True:
        pos = content.find(old_string, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1
    return positions


def _create_backup(file_path: str) -> str | None:
    """创建备份文件，返回备份路径"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{file_path}.bak.{timestamp}"
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception as e:
        return None


def execute_file_edit(arguments: dict, task=None) -> str:
    file_path = arguments.get("file_path", "")
    old_string = arguments.get("old_string", "")
    new_string = arguments.get("new_string", "")
    replace_all = arguments.get("replace_all", False)
    dry_run = arguments.get("dry_run", False)

    # ── 参数校验 ──
    if not file_path:
        return json.dumps({"type": "error", "content": "❌ file_path 不能为空"})
    if not old_string.strip():
        return json.dumps({"type": "error", "content": "❌ old_string 不能为空"})
    if old_string == new_string:
        return json.dumps({"type": "error", "content": "❌ old_string 和 new_string 必须不同"})

    # ── 路径安全校验 ──
    try:
        project_root = resolve_project_root(task)
        file_path = validate_path(file_path, project_root)
    except ValueError as e:
        return json.dumps({"type": "error", "content": str(e)})

    # ── 检查文件是否存在 ──
    if not os.path.isfile(file_path):
        return json.dumps({"type": "error", "content": f"❌ 文件不存在: {file_path}"})

    # ── 读取文件内容 ──
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            original_content = f.read()
    except Exception as e:
        return json.dumps({"type": "error", "content": f"❌ 读取文件失败: {e}"})

    # ── 查找匹配 ──
    content_normalized = _normalize_line_endings(original_content)
    old_normalized = _normalize_line_endings(old_string)

    positions = _find_all_occurrences(content_normalized, old_normalized)

    if not positions:
        return json.dumps({"type": "error", "content": f"❌ 在文件中未找到匹配的文本。请检查 old_string 是否与文件内容完全一致（包括缩进和换行）。"})

    if len(positions) > 1 and not replace_all:
        return json.dumps({
            "type": "error",
            "content": f"❌ 找到 {len(positions)} 处匹配项。请设置 replace_all=true 替换全部，或调整 old_string 使其唯一匹配。"
        })

    # ── 执行替换 ──
    if replace_all:
        new_content = content_normalized.replace(old_normalized, new_string)
    else:
        new_content = content_normalized.replace(old_normalized, new_string, 1)

    # ── 生成 diff 预览 ──
    diff_text = _generate_diff(file_path, content_normalized, new_content)
    lines_changed = new_content.count("\n") - content_normalized.count("\n")

    # ── dry run ──
    if dry_run:
        return json.dumps({
            "type": "text",
            "content": f"📋 **Dry Run — 变更预览**\n\n文件: `{file_path}`\n匹配: {len(positions)} 处\n行数变化: {lines_changed:+d}\n\n```diff\n{diff_text}\n```"
        })

    # ── 创建备份 ──
    backup_path = _create_backup(file_path)

    # ── 写入新内容 ──
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return json.dumps({"type": "error", "content": f"❌ 写入文件失败: {e}"})

    # ── 返回结果 ──
    match_count = len(positions)
    result = {
        "type": "text",
        "content": (
            f"✅ **文件编辑成功**\n\n"
            f"文件: `{file_path}`\n"
            f"操作: {'替换全部' if replace_all else '替换首处'} ({match_count} 处匹配)\n"
            f"行数变化: {lines_changed:+d}\n"
            f"{'备份: `' + backup_path + '`' if backup_path else '⚠️ 备份失败'}\n\n"
            f"```diff\n{diff_text}\n```"
        )
    }
    return json.dumps(result, ensure_ascii=False)
