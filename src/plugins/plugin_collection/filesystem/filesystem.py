import shutil
import mimetypes
import base64
import os
import json
import subprocess
import ast
import itertools
from typing import Optional, Any, List

MAX_READ_WINDOW = 200
MAX_EDITABLE_FILE_SIZE = 5 * 1024 * 1024
MAX_MEDIA_SIZE = 20 * 1024 * 1024
file_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "data\\config\\file_config.json")
with open(file_config_path, "r", encoding="utf-8") as f:
    config = json.load(f)
_SANDBOX_DIRS: List[str] = config["sandbox_dirs"]
_SKILL_DIRS: List[str] = config["skill_dir"]
_DONT_READ_DIRS: List[str] = config["dont_read_dirs"]
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
    _SANDBOX_DIRS.extend([os.path.abspath(d) for d in directories])
    config["sandbox_dirs"] = _SANDBOX_DIRS
    with open(file_config_path, "w", encoding="utf-8") as f:
        f.write(config)
    return _format_response("text", f"sandbox directories set to: {_SANDBOX_DIRS}")

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
def read_media_file(path: str) -> str:
    if not _get_allow("read", path):
        return _format_response("error", f"Permission denied: Reading {path} is blocked by sandbox.")
    if not os.path.exists(path):
        return _format_response("error", f"File not found: {path}")
    if os.path.getsize(path) > MAX_MEDIA_SIZE:
        return _format_response("error", f"Media file too large. Max allowed is {MAX_MEDIA_SIZE//1024//1024}MB.")
    try:
        mime_type, _ = mimetypes.guess_type(path)
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        content = {
            "mime_type": mime_type or "application/octet-stream",
            "data": data
        }
        return _format_response("media", content)
    except Exception as e:
        return _format_response("error", f"Failed to read media file: {str(e)}")

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
