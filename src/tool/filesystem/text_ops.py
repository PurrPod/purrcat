import os
import re
from pathlib import PurePath
from src.tool.filesystem.exceptions import (
    FileSystemError,
    HostPathNotFoundError,
)
from src.tool.filesystem.utils import resolve_safe_path, check_allowed, load_blacklist

MAX_LINES_TO_READ = 2000


def read_file(path_from: str, offset: int = 0, limit: int = MAX_LINES_TO_READ) -> dict:
    """Read 工具：支持纯文本读取，遇到富文本/二进制自动使用 markitdown 转换为 Markdown"""
    target_path = resolve_safe_path(path_from)

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
    """Edit 工具：安全的局部字符串精准替换"""
    if not old_string:
        raise FileSystemError("old_string 不能为空。")

    target_path = resolve_safe_path(path_from)
    if not os.path.exists(target_path):
        raise HostPathNotFoundError(target_path)

    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()

    occurrences = content.count(old_string)
    if occurrences == 0:
        raise FileSystemError(
            "⚠️ Edit 失败: old_string 在文件中未找到。\n"
            "原因：可能包含了行号前缀、缩进空格不匹配，或者文件在你上一次 read 后已被修改。\n"
            "解决：请检查旧字符串，确保不要包含 '101 | ' 这样的行号前缀，并保留原有的所有空格/换行。"
        )
    if occurrences > 1 and not replace_all:
        raise FileSystemError(
            f"⚠️ Edit 失败: old_string 在文件中出现了 {occurrences} 次，无法精确定位。\n"
            "解决：请在 old_string 中包含更多的上下文（如相邻的 2-4 行代码）以使其唯一。如果你确实想替换所有匹配项，请设置 replace_all=True。"
        )

    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return {
        "path": target_path,
        "message": f"成功更新文件 {os.path.basename(target_path)}",
        "replaced_occurrences": occurrences if replace_all else 1,
    }


def write_file(path_from: str, content: str) -> dict:
    """Write 工具：全量覆盖写入或创建新文件"""
    if content is None:
        raise FileSystemError("写入内容(content)不能为空。")

    target_path = resolve_safe_path(path_from)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "path": target_path,
        "message": f"成功写入文件 {os.path.basename(target_path)} (长度: {len(content)})",
    }


def search_file(path_from: str, pattern: str) -> dict:
    """Grep 工具：安全的正则全局搜索"""
    search_dir = resolve_safe_path(path_from)
    if not os.path.exists(search_dir) or not os.path.isdir(search_dir):
        raise FileSystemError(f"Grep 搜索目录无效: {search_dir}")

    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise FileSystemError(f"正则表达式无效: {e}")

    blacklist = load_blacklist()
    matches = []

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [d for d in dirs if check_allowed(os.path.join(root, d), blacklist)]

        for file in files:
            file_path = os.path.join(root, file)
            if not check_allowed(file_path, blacklist):
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
    search_dir = resolve_safe_path(path_from)
    blacklist = load_blacklist()
    matched_paths = []

    def walk_onerror(os_error):
        pass

    for root, dirs, files in os.walk(search_dir, onerror=walk_onerror):
        dirs[:] = [d for d in dirs if check_allowed(os.path.join(root, d), blacklist)]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, search_dir)
            if PurePath(rel_path).match(pattern):
                try:
                    if check_allowed(file_path, blacklist) and os.path.isfile(
                        file_path
                    ):
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
