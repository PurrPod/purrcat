import shutil
import mimetypes
import base64
import os
import json
import subprocess
import ast
import itertools
from typing import Optional, Any, List
from src.utils.config import FILE_CONFIG_PATH

MAX_READ_WINDOW = 200
MAX_EDITABLE_FILE_SIZE = 5 * 1024 * 1024
MAX_MEDIA_SIZE = 20 * 1024 * 1024

try:
    with open(FILE_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {
        "sandbox_dirs": ["sandbox/", "agent_vm/"],
        "skill_dir": ["data/skill"],
        "dont_read_dirs": ["src/"]
    }
    # Ensure directory exists and write default config
    os.makedirs(os.path.dirname(FILE_CONFIG_PATH), exist_ok=True)
    with open(FILE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

_SANDBOX_DIRS: List[str] = [os.path.abspath(d) for d in config.get("sandbox_dirs", [])]
_SKILL_DIRS: List[str] = [os.path.abspath(d) for d in config.get("skill_dir", [])]
_DONT_READ_DIRS: List[str] = [os.path.abspath(d) for d in config.get("dont_read_dirs", [])]
def _get_allow(action: str, path: str) -> bool:
    abs_path = os.path.abspath(path)
    if action == "read":
        if abs_path in _DONT_READ_DIRS:
            return False
        return True
    for allowed_dir in _SANDBOX_DIRS:
        try:
            if os.path.commonpath([allowed_dir, abs_path]) == allowed_dir:
                return True
        except ValueError:
            continue
    return False

def set_allowed_directories(directories: List[str]) -> str:
    global _SANDBOX_DIRS
    # Use a set to deduplicate paths and only store absolute paths
    new_dirs = set(_SANDBOX_DIRS)
    added = []
    skipped = []
    for d in directories:
        abs_path = os.path.abspath(d)
        if os.path.exists(abs_path) and os.path.isdir(abs_path):
            if abs_path not in new_dirs:
                new_dirs.add(abs_path)
                added.append(abs_path)
        else:
            skipped.append(d)
    _SANDBOX_DIRS = sorted(list(new_dirs))
    config["sandbox_dirs"] = _SANDBOX_DIRS
    with open(FILE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    message = f"sandbox directories set to: {_SANDBOX_DIRS}"
    if added:
        message += f"\nAdded: {added}"
    if skipped:
        message += f"\nSkipped (do not exist): {skipped}"
    return _format_response("text", message)

def list_special_directories() -> str:
    result = {"sandbox_dirs": _SANDBOX_DIRS, "skill_dir": _SKILL_DIRS, "dont_read_dirs": _DONT_READ_DIRS}
    return _format_response("text", result)

def write_text_file(path: str, content: str) -> str:
    if not _get_allow("write", path):
        return _format_response("error", f"Permission denied: Writing to {path} is blocked by sandbox.")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        lint = _silent_lint_file(path)
        if lint:
            return _format_response("warning", f"Wrote successfully but lint failed:\n{lint}")
        return _format_response("text", f"Successfully wrote to {path}")
    except Exception as e:
        return _format_response("error", f"Failed to write file: {str(e)}")


def list_file_in_dir(path: str) -> str:
    if not _get_allow("read", path):
        return _format_response("error", f"Permission denied: Reading {path} is blocked by sandbox.")
    if not os.path.exists(path):
        return _format_response("error", f"Path not found: {path}")
    if not os.path.isdir(path):
        return _format_response("error", f"Not a directory: {path}")
    try:
        items = os.listdir(path)
        if not items:
            return _format_response("text", f"Empty directory: {path}")
        dirs = [d for d in items if os.path.isdir(os.path.join(path, d))]
        files = [f for f in items if os.path.isfile(os.path.join(path, f))]
        res = f"[{path}] (Dirs: {len(dirs)}, Files: {len(files)})\n"
        if dirs:
            res += "[Dirs]: " + ", ".join(dirs) + "\n"
        if files:
            res += "[Files]: " + ", ".join(files)
        if len(res) > 600:
            res = res[:600] + "\n... (Output truncated)"
        return _format_response("text", res.strip())
    except Exception as e:
        return _format_response("error", f"Failed to list directory: {str(e)}")


import uuid
import datetime


# 注意：如果你文件开头还没导入这两个库，记得加上

def parse_document(path: str) -> str:
    """使用 MarkItDown 解析各种非纯文本的富文本文档（并支持超长内容 Buffer 暂存）"""
    if not _get_allow("read", path):
        return _format_response("error", f"Permission denied: Reading {path} is blocked by sandbox.")
    if not os.path.exists(path):
        return _format_response("error", f"File not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    text_extensions = {
        ".txt", ".csv", ".tsv", ".json", ".md", ".py", ".js",
        ".html", ".css", ".yaml", ".yml", ".xml", ".sh", ".log", ".ini"
    }
    if ext in text_extensions:
        return _format_response("error",f"File '{path}' is a plain text or CSV file. Please use 'filesystem__read_file_lines' or 'filesystem__search_in_file' to read it directly.")
    if os.path.getsize(path) > MAX_MEDIA_SIZE:
        return _format_response("error", f"File too large to parse. Max allowed is {MAX_MEDIA_SIZE // 1024 // 1024}MB.")
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(path)
        text_content = result.text_content
        if not text_content or not text_content.strip():
            return _format_response("warning","Parsed successfully, but the document appears to be empty or contains no extractable text.")
        max_chars = 15000
        if len(text_content) > max_chars:
            buffer_dir = os.path.abspath(os.path.join(os.path.dirname(FILE_CONFIG_PATH), "..", "buffer"))
            os.makedirs(buffer_dir, exist_ok=True)
            marker_id = uuid.uuid4().hex[:8]
            timestamp = datetime.datetime.now().strftime("%Y%m%d")
            buffer_filename = f"parsed_{timestamp}_{marker_id}.md"
            buffer_path = os.path.join(buffer_dir, buffer_filename)
            with open(buffer_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(text_content)
            preview = text_content[:3000]
            return _format_response(
                "text",
                f"{preview}\n\n"
                f"...\n\n"
                f"==================================================\n"
                f"⚠️ [注意] 文档内容过长（共 {len(text_content)} 字符）。\n"
                f"为防止上下文溢出，完整解析结果已转换为 Markdown 并保存至本地文件：\n"
                f"📂 {buffer_path}\n"
                f"👆 如果你需要阅读后续内容，请务必使用 'filesystem__read_file_lines' 或 'filesystem__search_in_file' 工具来读取上述文件。\n"
                f"=================================================="
            )
        return _format_response("text", text_content.strip())
    except ImportError:
        return _format_response("error","The 'markitdown' library is not installed. Please run: pip install markitdown[all]")
    except Exception as e:
        return _format_response("error", f"MarkItDown failed to parse {path}: {str(e)}")

def delete_file(path: str) -> str:
    if not _get_allow("delete", path):
        return _format_response("error", f"Permission denied: Deleting {path} is blocked by sandbox.")
    if not os.path.lexists(path):
        return _format_response("error", f"Path not found: {path}")
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        return _format_response("text", f"Successfully deleted {path}")
    except Exception as e:
        return _format_response("error", f"Failed to delete: {str(e)}")

def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)

def _silent_lint_file(path: str) -> Optional[str]:
    """带有 Timeout 的安全 Lint，防止大文件卡死系统"""
    if not os.path.exists(path):
        return None
    if os.path.getsize(path) > MAX_EDITABLE_FILE_SIZE:
        return None
    ext = os.path.splitext(path)[1].lower()
    # Python
    if ext == ".py":
        try:
            result = subprocess.run(["ruff", "check", path], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return result.stdout
            return None
        except FileNotFoundError:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    ast.parse(f.read())
                return None
            except SyntaxError as e:
                return f"Python syntax error line {e.lineno}: {e.msg}"
        except subprocess.TimeoutExpired:
            return "Linter timeout exceeded."

    # JS / TS
    if ext in [".js", ".ts"]:
        try:
            result = subprocess.run(["eslint", "--no-eslintrc", path], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # JSON
    if ext == ".json":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                json.load(f)
            return None
        except json.JSONDecodeError as e:
            return f"JSON error line {e.lineno}: {e.msg}"

    return None


def read_file_lines(path: str, start: int, end: int) -> str:
    if not _get_allow("read", path):
        return _format_response("error", f"Permission denied: Reading {path} is blocked by sandbox.")
    if not os.path.exists(path):
        return _format_response("error", f"File not found: {path}")
    file_size = os.path.getsize(path)
    if file_size > MAX_EDITABLE_FILE_SIZE:
        return _format_response("error",
                                f"File too large ({file_size / 1024 / 1024:.1f}MB). Max allowed is 5MB. Please use 'shell' tools like 'head', 'tail', or 'grep'.")
    try:
        start = max(1, start)
        if end - start + 1 > MAX_READ_WINDOW:
            end = start + MAX_READ_WINDOW - 1

        snippet_lines = []
        total_lines = 0
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            total_lines = sum(1 for _ in f)
        end = min(end, total_lines)
        width = len(str(total_lines))
        truncated = (end - start + 1) == MAX_READ_WINDOW
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(itertools.islice(f, start - 1, end), start):
                snippet_lines.append(f"{i:>{width}} | {line.rstrip()}")
        if truncated and end < total_lines:
            snippet_lines.append(f"{'':>{width}} | ... (Output truncated to {MAX_READ_WINDOW} lines)")
        result = {
            "path": path,
            "start": start,
            "end": end,
            "total_lines": total_lines,
            "snippet": "\n".join(snippet_lines),
        }
        return _format_response("text", result)
    except Exception as e:
        return _format_response("error", f"Failed to read file: {str(e)}")


def search_in_file(path: str, keyword: str, limit: int = 20) -> str:
    if not _get_allow("read", path):
        return _format_response("error", f"Permission denied: Reading {path} is blocked by sandbox.")
    if not os.path.exists(path):
        return _format_response("error", "File not found")
    if os.path.getsize(path) > MAX_EDITABLE_FILE_SIZE:
        return _format_response("error", "File too large. Please use 'shell' tool with 'grep' command instead.")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            total_lines = sum(1 for _ in f)
        width = len(str(total_lines))
        snippet_lines = []
        match_count = 0
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if keyword.lower() in line.lower():
                    snippet_lines.append(f"{i:>{width}} | {line.rstrip()}")
                    match_count += 1
                if match_count >= limit:
                    snippet_lines.append(f"{'':>{width}} | ... (Reached limit of {limit} matches)")
                    break
        snippet = "\n".join(snippet_lines) if snippet_lines else "No matches found."
        result = {
            "path": path,
            "keyword": keyword,
            "total_matches": match_count,
            "total_lines": total_lines,
            "snippet": snippet
        }
        return _format_response("text", result)
    except Exception as e:
        return _format_response("error", str(e))


def replace_file_lines(path: str, start: int, end: int, new_code: str) -> str:
    if not os.path.exists(path):
        return _format_response("error", "File not found")
    if not _get_allow("overwrite", path):
        return _format_response("error", f"Permission denied: Modifying {path} is not allowed by sandbox.")
    if os.path.getsize(path) > MAX_EDITABLE_FILE_SIZE:
        return _format_response("error",
                                "File too large for in-line replacement. Please write a Python script to process it.")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        if start < 1 or end > total or start > end:
            return _format_response("error", f"Invalid range {start}-{end}. File has {total} lines.")
        new_lines = new_code.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        lines[start - 1:end] = new_lines
        temp_path = path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        os.replace(temp_path, path)  # Windows/Linux 均支持原子替换
        lint = _silent_lint_file(path)
        if lint:
            return _format_response("warning", f"Lines replaced but lint failed:\n{lint}")
        return _format_response("text", f"Successfully replaced lines {start}-{end}")
    except Exception as e:
        return _format_response("error", str(e))
