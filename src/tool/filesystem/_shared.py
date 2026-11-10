"""文件工具的共享纯函数。

集中行尾处理、原子写入、统一 diff 与遍历过滤规则，避免 text_ops /
filesystem / history 三处各写一份。
"""

from __future__ import annotations

import difflib
import os
import tempfile

from .exceptions import FileSystemError

# search 遍历时跳过的目录与二进制扩展名
IGNORE_DIRS = {
    "node_modules",
    "__pycache__",
    "venv",
    "env",
    "dist",
    "build",
    "target",
}

IGNORE_EXTS = (
    ".jpg",
    ".png",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".mp4",
    ".pyc",
    ".exe",
    ".dll",
)


def normalize_newlines(text: str) -> str:
    """归一化行尾为 \\n（匹配与替换统一在 \\n 口径进行）。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect_dominant_newline(raw: bytes) -> str:
    """检测字节内容的主导行尾：CRLF 占多数则返回 CRLF，否则 LF。"""
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def apply_newline_style(text: str, dominant_nl: str) -> str:
    """按文件原主导行尾写回；LF 保持原样，避免无意义替换。"""
    if dominant_nl != "\n":
        return text.replace("\n", dominant_nl)
    return text


def build_lock_path(target_path: str, lock_dir: str) -> str:
    """生成目标文件独占的锁文件路径（去掉 Windows 盘符冒号）。"""
    safe_lock_name = target_path.replace(os.sep, "%").replace(":", "") + ".lock"
    return os.path.join(lock_dir, safe_lock_name)


def atomic_write_text(target_path: str, text: str) -> None:
    """同目录临时文件 + os.replace 原子覆盖；失败时清理临时文件。"""
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(target_path), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(temp_path, target_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def format_diff_path(path_from: str) -> str:
    """展示路径统一带前导 /，确保 diff 头可被 Agent 直接用作 read 路径。"""
    return path_from if path_from.startswith("/") else "/" + path_from


def build_diff(old_text: str, new_text: str, path_from: str) -> str:
    """生成统一 diff 文本（3 行上下文）。"""
    format_path = format_diff_path(path_from)
    diff_lines = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a{format_path}",
        tofile=f"b{format_path}",
        n=3,
    )
    return "".join(diff_lines)


def summarize_diff(diff_text: str) -> str:
    """解析 unified diff，统计新增/删除的代码行数。"""
    if not diff_text:
        return "新增 0 行，删除 0 行"

    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return f"新增了 {additions} 行代码，删除了 {deletions} 行代码"


def select_line_window(lines: list[str], offset: int, limit: int) -> tuple[int, int]:
    """把读取窗口夹紧到 [0, total] 区间。"""
    total_lines = len(lines)
    start = max(0, offset)
    end = min(total_lines, start + limit)
    return start, end


def replace_occurrences(
    content: str, old_string: str, new_string: str, replace_all: bool
) -> tuple[str, int]:
    """执行替换并返回 (新内容, 命中次数)；命中 0 或多次非全量时抛错。"""
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

    if replace_all:
        return content.replace(old_string, new_string), occurrences
    return content.replace(old_string, new_string, 1), occurrences


def should_skip_dir(name: str) -> bool:
    return name.startswith(".") or name in IGNORE_DIRS


def should_skip_file(name: str) -> bool:
    return name.startswith(".") or name.endswith(IGNORE_EXTS)
