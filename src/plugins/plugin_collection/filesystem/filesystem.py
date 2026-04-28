import shutil
import mimetypes
import base64
import os
import json
import subprocess
import ast
import itertools
from typing import Optional, Any, List
from src.utils.config import get_filesystem_config

MAX_READ_WINDOW = 200
MAX_EDITABLE_FILE_SIZE = 5 * 1024 * 1024
MAX_MEDIA_SIZE = 20 * 1024 * 1024

_fs_cfg = get_filesystem_config()
_SANDBOX_DIRS: List[str] = [os.path.abspath(d) for d in _fs_cfg.get("sandbox_dirs", ["sandbox/", "agent_vm/"])]
_SKILL_DIRS: List[str] = [os.path.abspath(d) for d in _fs_cfg.get("skill_dir", ["data/skill"])]
_DONT_READ_DIRS: List[str] = [os.path.abspath(d) for d in _fs_cfg.get("dont_read_dirs", ["src/"])]
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
    config_dict = {"sandbox_dirs": _SANDBOX_DIRS, "skill_dir": _SKILL_DIRS, "dont_read_dirs": _DONT_READ_DIRS}
    message = f"sandbox directories set to: {_SANDBOX_DIRS}"
    if added:
        message += f"\nAdded: {added}"
    if skipped:
        message += f"\nSkipped (do not exist): {skipped}"
    return _format_response("text", message)



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
        return _format_response("text", res.strip())
    except Exception as e:
        return _format_response("error", f"Failed to list directory: {str(e)}")


import uuid
import datetime


# 注意：如果你文件开头还没导入这两个库，记得加上

def parse_document(path: str) -> str:
    """使用 MarkItDown 解析各种非纯文本的富文本文档"""
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
        # 超长输出由上层 parse_tool 统一处理
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


def copy_item_to(host_file_paths: List[str], vm_dir_path: str) -> str:
    """
    将主机文件批量复制到虚拟机目录下
    
    Args:
        host_file_paths: 主机的文件路径列表
        vm_dir_path: 虚拟机目录路径，格式为 /agent_vm/xxx
        
    Returns:
        操作结果的JSON字符串
    """
    # 验证虚拟机目录路径格式
    if not vm_dir_path.startswith('/agent_vm/'):
        return _format_response("error", f"虚拟机目录路径必须以 '/agent_vm/' 开头，当前路径: {vm_dir_path}")
    
    # 转换虚拟机路径为实际主机路径
    # 去掉开头的 /agent_vm/，得到相对路径
    relative_path = vm_dir_path[len('/agent_vm/'):]
    if not relative_path:
        return _format_response("error", "虚拟机目录路径不能为空")
    
    # 构建实际的目标目录路径
    # 从项目根目录开始构建agent_vm路径
    # 使用BASE_DIR或从当前文件位置向上查找
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 向上查找直到找到包含agent_vm目录的目录
    project_root = current_dir
    while project_root and not os.path.exists(os.path.join(project_root, 'agent_vm')):
        parent = os.path.dirname(project_root)
        if parent == project_root:  # 到达根目录
            break
        project_root = parent
    
    if not project_root or not os.path.exists(os.path.join(project_root, 'agent_vm')):
        # 回退到原来的计算方法
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    target_dir = os.path.join(project_root, 'agent_vm', relative_path)
    target_dir = os.path.abspath(target_dir)
    
    # 检查目标目录是否存在且在沙箱范围内
    if not _get_allow("write", target_dir):
        return _format_response("error", f"目标目录不在沙箱允许范围内: {target_dir}")
    
    # 确保目标目录存在
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        return _format_response("error", f"无法创建目标目录: {str(e)}")
    
    copied_files = []
    failed_files = []
    
    for host_path in host_file_paths:
        try:
            # 检查源文件是否存在
            if not os.path.exists(host_path):
                failed_files.append(f"{host_path}: 文件不存在")
                continue
            
            # 检查源文件是否可读
            if not os.access(host_path, os.R_OK):
                failed_files.append(f"{host_path}: 文件不可读")
                continue
            
            # 获取文件名
            filename = os.path.basename(host_path)
            target_path = os.path.join(target_dir, filename)
            
            # 检查是否会覆盖现有文件
            if os.path.exists(target_path):
                # 可以选择重命名或跳过，这里选择重命名
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(target_dir, f"{base}_{counter}{ext}")):
                    counter += 1
                target_path = os.path.join(target_dir, f"{base}_{counter}{ext}")
            
            # 复制文件
            if os.path.isdir(host_path):
                shutil.copytree(host_path, target_path)
            else:
                shutil.copy2(host_path, target_path)
            
            copied_files.append(f"{host_path} -> {target_path}")
            
        except Exception as e:
            failed_files.append(f"{host_path}: {str(e)}")
    
    result = {
        "target_directory": target_dir,
        "total_files": len(host_file_paths),
        "copied_files": copied_files,
        "failed_files": failed_files,
        "success_count": len(copied_files),
        "failure_count": len(failed_files)
    }
    
    if failed_files:
        return _format_response("warning", result)
    else:
        return _format_response("text", result)


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
        snippet_lines = []
        total_lines = 0
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            total_lines = sum(1 for _ in f)
        end = min(end, total_lines)
        width = len(str(total_lines))
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(itertools.islice(f, start - 1, end), start):
                snippet_lines.append(f"{i:>{width}} | {line.rstrip()}")
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
