import os
import re
import hashlib
import json
from pathlib import PurePath
from filelock import FileLock, Timeout
from src.tool.filesystem import _shared
from src.tool.filesystem.checker import run_code_check, count_code_check_issues
from src.tool.filesystem.exceptions import (
    FileSystemError,
    HostPathNotFoundError,
)
from src.tool.filesystem.utils import require_read, require_write, is_readable
from src.tool.filesystem.history import track_edit, save_backup_meta
from src.utils.config import PURRCAT_DIR, BUFFER_DIR, AGENT_VM_DIR

MAX_LINES_TO_READ = 2000

LOCK_DIR = os.path.join(PURRCAT_DIR, ".agent_locks")
os.makedirs(LOCK_DIR, exist_ok=True)

CACHE_DIR = os.path.join(BUFFER_DIR, "filesystem")
REGISTRY_FILE = os.path.join(CACHE_DIR, "registry.json")

# 代码检查报告落盘目录（放在沙盒 buffer 内，避免污染用户项目）
CHECK_REPORT_DIR = os.path.join(BUFFER_DIR, "filesystem", "lint")


def _save_check_report(target_path: str, report: str) -> str:
    """把完整检查报告写入 buffer 文件，返回 Agent 视角可读的沙盒路径"""
    os.makedirs(CHECK_REPORT_DIR, exist_ok=True)
    path_hash = hashlib.md5(target_path.encode("utf-8")).hexdigest()[:8]
    report_path = os.path.join(
        CHECK_REPORT_DIR, f"{os.path.basename(target_path)}.{path_hash}.lint.txt"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 代码检查报告: {target_path}\n\n{report}\n")

    rel = os.path.relpath(report_path, AGENT_VM_DIR).replace(os.sep, "/")
    return f"/agent_vm/{rel}"


def _get_cache(target_path: str, current_mtime: float):
    """读取缓存文件并验证修改时间是否一致"""
    if not os.path.exists(REGISTRY_FILE):
        return None, False

    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, False

    file_cache = registry.get(target_path)
    if not file_cache:
        return None, False

    if file_cache.get("mtime") != current_mtime:
        return None, False

    cache_path = file_cache.get("cache_path")
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.readlines(), file_cache.get("is_converted", False)
        except OSError:
            pass

    return None, False


def _set_cache(target_path: str, lines: list, current_mtime: float, is_converted: bool):
    """写入解析结果到缓存文件，并更新注册表"""
    os.makedirs(CACHE_DIR, exist_ok=True)

    path_hash = hashlib.md5(target_path.encode("utf-8")).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{path_hash}.cache.txt")

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except OSError:
        return

    registry_lock = FileLock(REGISTRY_FILE + ".lock", timeout=5)
    try:
        with registry_lock:
            registry = {}
            if os.path.exists(REGISTRY_FILE):
                try:
                    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                        registry = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

            registry[target_path] = {
                "mtime": current_mtime,
                "cache_path": cache_path,
                "is_converted": is_converted,
            }

            with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)
    except Timeout:
        pass


def read_file(path_from: str, offset: int = 0, limit: int = MAX_LINES_TO_READ) -> dict:
    """Read 工具：支持纯文本读取，遇到富文本/二进制自动转换为 Markdown"""
    target_path = require_read(path_from)

    if not os.path.exists(target_path):
        raise HostPathNotFoundError(target_path)
    if not os.path.isfile(target_path):
        raise FileSystemError(
            f"目标不是一个文件: {target_path}。如果是目录请使用 list。"
        )

    current_mtime = os.path.getmtime(target_path)

    cached_lines, is_converted = _get_cache(target_path, current_mtime)

    if cached_lines is not None:
        lines = cached_lines
    else:
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
                    "提示：宿主机未安装 markitdown"
                )
            except Exception as e:
                raise FileSystemError(
                    f"文件读取失败。既不是有效的纯文本，MarkItDown也无法解析: {str(e)}"
                )

        _set_cache(target_path, lines, current_mtime, is_converted)

    total_lines = len(lines)
    start, end = _shared.select_line_window(lines, offset, limit)

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

    lock_path = _shared.build_lock_path(target_path, LOCK_DIR)
    lock = FileLock(lock_path, timeout=15)

    try:
        with lock:
            # 🌟 字节级读取：检测原始行尾风格，杜绝 Windows 文本模式把 LF 改写成 CRLF
            with open(target_path, "rb") as f:
                raw_content = f.read()
            dominant_nl = _shared.detect_dominant_newline(raw_content)
            content = _shared.normalize_newlines(raw_content.decode("utf-8"))

            # 匹配口径统一为 \n（read 展示给 Agent 的也是归一化内容）
            old_string = _shared.normalize_newlines(old_string)
            new_string = _shared.normalize_newlines(new_string)

            new_content, occurrences = _shared.replace_occurrences(
                content, old_string, new_string, replace_all
            )

            backup_id = track_edit(target_path)

            # newline="" 禁用平台行尾转换，按文件原主导行尾写回
            _shared.atomic_write_text(
                target_path,
                _shared.apply_newline_style(new_content, dominant_nl),
            )

    except Timeout:
        raise FileSystemError("文件正被其他 Agent 锁定修改，请稍后重试！")

    # 🌟 修复点：在 Diff 头中注入完整的相对/沙盒路径，不要用 basename
    diff_text = _shared.build_diff(content, new_content, path_from)
    save_backup_meta(
        target_path, backup_id, diff_text
    )  # 🌟 核心：保存 metadata 供全局读取

    check_result = run_code_check(target_path)
    msg = f"成功更新文件 {os.path.basename(target_path)}"
    if check_result:
        report_path = _save_check_report(target_path, check_result)
        issue_count = count_code_check_issues(check_result)
        msg += (
            f"\n\n🔎 代码检查到 {issue_count} 条问题，"
            f"完整 lint 报告见（可自行 read 查看）：{report_path}"
        )

    return {
        "path": target_path,
        "backup_id": backup_id,
        "message": msg,
        "replaced_occurrences": occurrences if replace_all else 1,
        "diff": diff_text,  # 修改为 diff_text
    }


def write_file(path_from: str, content: str) -> dict:
    """Write 工具：全量覆盖写入或创建新文件（支持文件锁和原子写入），带完整 Diff"""
    if content is None:
        raise FileSystemError("写入内容(content)不能为空。")

    target_path = require_write(path_from)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    lock_path = _shared.build_lock_path(target_path, LOCK_DIR)
    lock = FileLock(lock_path, timeout=15)

    try:
        with lock:
            # 🌟 1. 在覆盖前，先字节级读取旧文件（如存在）：检测行尾风格供写回适配
            old_content = ""
            dominant_nl = "\n"
            if os.path.exists(target_path):
                with open(target_path, "rb") as f:
                    old_raw = f.read()
                dominant_nl = _shared.detect_dominant_newline(old_raw)
                old_content = _shared.normalize_newlines(old_raw.decode("utf-8"))

            backup_id = track_edit(target_path)

            # 归一化后按旧文件主导行尾适配（新文件保持 LF），杜绝平台行尾转换
            norm_content = _shared.normalize_newlines(content)
            _shared.atomic_write_text(
                target_path,
                _shared.apply_newline_style(norm_content, dominant_nl),
            )

    except Timeout:
        raise FileSystemError("文件正被其他 Agent 锁定修改，请稍后重试！")

    # 🌟 2. 使用 difflib 计算全量覆盖的真实 Diff
    diff_text = _shared.build_diff(old_content, norm_content, path_from)
    save_backup_meta(
        target_path, backup_id, diff_text
    )  # 🌟 核心：保存 metadata 供全局读取

    msg = f"成功写入文件 {os.path.basename(target_path)} (长度: {len(content)})"

    return {
        "path": target_path,
        "backup_id": backup_id,
        "message": msg,
        "diff": diff_text,  # 修改为 diff_text
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
    MAX_MATCHES = 50

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [
            d
            for d in dirs
            if not _shared.should_skip_dir(d) and is_readable(os.path.join(root, d))
        ]

        for file in files:
            if _shared.should_skip_file(file):
                continue

            file_path = os.path.join(root, file)
            if not is_readable(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if regex.search(line):
                            rel_path = os.path.relpath(file_path, search_dir)
                            matches.append(f"{rel_path}:{i + 1}:{line.strip()}")
                            if len(matches) >= MAX_MATCHES:
                                break
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

            if len(matches) >= MAX_MATCHES:
                break

        if len(matches) >= MAX_MATCHES:
            matches.append(
                "... [搜索结果过多，已截断前50条。请使用更精确的 pattern，或指定更深层的目录进行精准搜索]"
            )
            break

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
