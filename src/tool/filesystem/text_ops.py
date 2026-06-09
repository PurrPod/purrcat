import os
import re
import difflib
import tempfile
from pathlib import PurePath
from filelock import FileLock, Timeout
from src.tool.filesystem.checker import run_code_check
from src.tool.filesystem.exceptions import (
    FileSystemError,
    HostPathNotFoundError,
)
from src.tool.filesystem.utils import require_read, require_write, is_readable
from src.tool.filesystem.history import track_edit

MAX_LINES_TO_READ = 2000

LOCK_DIR = os.path.join(os.getcwd(), ".agent_locks")
os.makedirs(LOCK_DIR, exist_ok=True)


def read_file(path_from: str, offset: int = 0, limit: int = MAX_LINES_TO_READ) -> dict:
    """Read 工具：支持纯文本读取，遇到富文本/二进制自动使用 markitdown 转换为 Markdown"""
    target_path = require_read(path_from)

    if not os.path.exists(target_path):
        raise HostPathNotFoundError(target_path)
    if not os.path.isfile(target_path):
        raise FileSystemError(
            f"目标不是一个文件: {target_path}。如果是目录请使用 list。"
        )

    lines = []
    is_converted = False

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    except UnicodeDecodeError:
        try:
            from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(target_path)
            if not result.text_content:
                raise FileSystemError("文件转换成功，但提取出的文本内容为空。")
            lines = [line + "\n" for line in result.text_content.split("\n")]
            is_converted = True

        except ImportError:
            raise FileSystemError(
                "文件似乎是二进制或富文本格式，无法直接读取。\n"
                "提示：宿主机未安装 markitdown。请联系管理员运行 `pip install markitdown` 来支持读取此类文件。"
            )
        except Exception as e:
            raise FileSystemError(
                f"文件读取失败。既不是有效的纯文本，MarkItDown也无法解析: {str(e)}"
            )

    total_lines = len(lines)
    start = max(0, offset)
    end = min(total_lines, start + limit)

    formatted_lines = []
    for i in range(start, end):
        formatted_lines.append(f"{i + 1:6d} | {lines[i]}")

    content = "".join(formatted_lines)

    msg = f"📄 读取了 {start + 1} to {end} 行"
    if is_converted:
        msg = "🔄 [已自动转为Markdown] " + msg

    return {
        "path": target_path,
        "is_converted_to_markdown": is_converted,
        "total_lines": total_lines,
        "showing_lines": f"{start + 1} to {end}",
        "content": content if content else "[文件内容为空]",
        "message": msg,
    }


def edit_file(
    path_from: str, old_string: str, new_string: str, replace_all: bool = False
) -> dict:
    """Edit 工具：安全的局部字符串精准替换（支持文件锁和原子写入）"""
    if not old_string:
        raise FileSystemError("old_string 不能为空。")

    target_path = require_write(path_from)
    if not os.path.exists(target_path):
        raise HostPathNotFoundError(target_path)

    safe_lock_name = target_path.replace(os.sep, "%").replace(":", "") + ".lock"
    lock_path = os.path.join(LOCK_DIR, safe_lock_name)
    lock = FileLock(lock_path, timeout=15)

    try:
        with lock:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()

            occurrences = content.count(old_string)
            if occurrences == 0:
                raise FileSystemError(
                    "⚠️ Edit 失败: old_string 在文件中未找到。文件已被其他 Agent 抢占修改！\n"
                    "解决：请重新 read 文件获取最新内容后再进行 edit。"
                )
            if occurrences > 1 and not replace_all:
                raise FileSystemError(
                    f"⚠️ Edit 失败: old_string 出现了 {occurrences} 次，无法精确定位。"
                )

            backup_id = track_edit(target_path)

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            fd, temp_path = tempfile.mkstemp(
                dir=os.path.dirname(target_path), text=True
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_content)
                os.replace(temp_path, target_path)
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e

    except Timeout:
        raise FileSystemError("文件正被其他 Agent 锁定修改，请稍后重试！")

    # 🌟 修复点：在 Diff 头中注入完整的相对/沙盒路径，不要用 basename
    format_path = path_from if path_from.startswith("/") else "/" + path_from
    diff_lines = list(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a{format_path}",
            tofile=f"b{format_path}",
            n=3,
        )
    )

    check_result = run_code_check(target_path)
    msg = f"成功更新文件 {os.path.basename(target_path)}"
    if check_result:
        msg += f"\n\n[代码检查报告]:\n{check_result}"

    return {
        "path": target_path,
        "backup_id": backup_id,
        "message": msg,
        "replaced_occurrences": occurrences if replace_all else 1,
        "diff": "".join(diff_lines),
    }


def write_file(path_from: str, content: str) -> dict:
    """Write 工具：全量覆盖写入或创建新文件（支持文件锁和原子写入），带完整 Diff"""
    if content is None:
        raise FileSystemError("写入内容(content)不能为空。")

    target_path = require_write(path_from)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    safe_lock_name = target_path.replace(os.sep, "%").replace(":", "") + ".lock"
    lock_path = os.path.join(LOCK_DIR, safe_lock_name)
    lock = FileLock(lock_path, timeout=15)

    try:
        with lock:
            # 🌟 1. 在覆盖前，先读取旧文件内容（如果存在的话）
            old_content = ""
            if os.path.exists(target_path):
                with open(target_path, "r", encoding="utf-8") as f:
                    old_content = f.read()

            backup_id = track_edit(target_path)

            fd, temp_path = tempfile.mkstemp(
                dir=os.path.dirname(target_path), text=True
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                os.replace(temp_path, target_path)
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e

    except Timeout:
        raise FileSystemError("文件正被其他 Agent 锁定修改，请稍后重试！")

    # 🌟 2. 使用 difflib 计算全量覆盖的真实 Diff
    format_path = path_from if path_from.startswith("/") else "/" + path_from
    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a{format_path}",
            tofile=f"b{format_path}",
            n=3,
        )
    )

    check_result = run_code_check(target_path)
    msg = f"成功写入文件 {os.path.basename(target_path)} (长度: {len(content)})"
    if check_result:
        msg += f"\n\n[系统自动代码检查报告]:\n{check_result}"

    return {
        "path": target_path,
        "backup_id": backup_id,
        "message": msg,
        "diff": "".join(diff_lines),  # 🌟 3. 将真实生成的 Diff 返回给前端
    }


def search_file(path_from: str, pattern: str) -> dict:
    """Grep 工具：安全的正则全局搜索"""
    search_dir = require_read(path_from)
    if not os.path.exists(search_dir) or not os.path.isdir(search_dir):
        raise FileSystemError(f"Grep 搜索目录无效: {search_dir}")

    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise FileSystemError(f"正则表达式无效: {e}")

    matches = []

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [d for d in dirs if is_readable(os.path.join(root, d))]

        for file in files:
            file_path = os.path.join(root, file)
            if not is_readable(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if regex.search(line):
                            rel_path = os.path.relpath(file_path, search_dir)
                            matches.append(f"{rel_path}:{i + 1}:{line.strip()}")
                            if len(matches) > 1000:
                                matches.append("... [搜索结果过多，已截断]")
                                break
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

    return {
        "search_dir": search_dir,
        "pattern": pattern,
        "match_count": len(matches),
        "results": "\n".join(matches) if matches else "未找到匹配项",
    }


def glob_file(path_from: str, pattern: str) -> dict:
    """Glob 工具：模式匹配并按时间排序 (免疫系统级破坏的增强版)"""
    search_dir = require_read(path_from)
    matched_paths = []

    def walk_onerror(os_error):
        pass

    for root, dirs, files in os.walk(search_dir, onerror=walk_onerror):
        dirs[:] = [d for d in dirs if is_readable(os.path.join(root, d))]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, search_dir)
            if PurePath(rel_path).match(pattern):
                try:
                    if is_readable(file_path) and os.path.isfile(file_path):
                        matched_paths.append(file_path)
                except OSError:
                    continue

    def safe_getmtime(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0

    matched_paths.sort(key=safe_getmtime, reverse=True)

    results = [
        os.path.relpath(x, search_dir).replace("\\", "/") for x in matched_paths[:100]
    ]

    return {
        "search_dir": search_dir,
        "pattern": pattern,
        "total_matches": len(matched_paths),
        "files_sorted_by_mtime": results,
    }
