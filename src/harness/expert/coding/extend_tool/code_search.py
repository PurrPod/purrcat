"""
code_search — 代码搜索工具（Glob + Grep 整合）

借鉴 Claude Code GlobTool + GrepTool 设计：
- 文件查找：支持 glob 通配符模式，按修改时间排序
- 内容搜索：基于 ripgrep（优先）/ grep（降级），支持正则和多行
- 搜索结果带上行号和上下文

两种模式：
  1. glob: 按文件名模式搜索
  2. grep: 按文件内容搜索（支持正则）
"""

import json
import os
import subprocess
import fnmatch
from pathlib import Path
from .path_utils import validate_path, resolve_project_root, validate_path_optional

CODE_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "code_search",
        "description": "搜索代码文件。支持两种模式：glob（按文件名匹配）和 grep（按内容搜索）。搜索结果自动去重排序。",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["glob", "grep"],
                    "description": "搜索模式：glob 按文件名查找，grep 按文件内容搜索"
                },
                "pattern": {
                    "type": "string",
                    "description": "glob 模式：如 '**/*.py'、'src/**/*.ts'；grep 模式：搜索的正则表达式或关键字"
                },
                "path": {
                    "type": "string",
                    "description": "搜索起始目录，默认当前工作目录"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，默认 30"
                },
                "include_ext": {
                    "type": "string",
                    "description": "（grep 模式）限定文件后缀，逗号分隔，如 '.py,.ts,.js'"
                },
                "context_lines": {
                    "type": "integer",
                    "description": "（grep 模式）匹配行上下文的行数，默认 2"
                },
                "fixed_string": {
                    "type": "boolean",
                    "description": "（grep 模式）将 pattern 视为普通字符串而非正则，默认 true"
                }
            },
            "required": ["mode", "pattern"]
        }
    }
}


def _glob_search(pattern: str, search_path: str, max_results: int) -> list[dict]:
    """按 glob 模式搜索文件"""
    results = []
    search_path = search_path or os.getcwd()

    # 支持 ** 递归匹配
    for root, dirs, files in os.walk(search_path):
        # 跳过隐藏目录和常见无源码目录
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", ".git", ".venv", "venv", "dist", "build", ".next",
            ".buffer", ".mypy_cache", ".pytest_cache"
        )]

        for f in files:
            if len(results) >= max_results:
                break
            rel_path = os.path.relpath(os.path.join(root, f), search_path)
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(f, pattern):
                full_path = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(full_path)
                    size = os.path.getsize(full_path)
                except OSError:
                    mtime = 0
                    size = 0
                results.append({
                    "path": rel_path,
                    "full_path": full_path,
                    "mtime": mtime,
                    "size": size,
                })

        if len(results) >= max_results:
            break

    # 按修改时间排序（最新的在前）
    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results[:max_results]


def _grep_search(pattern: str, search_path: str, max_results: int,
                 include_ext: str | None, context_lines: int,
                 fixed_string: bool) -> list[dict]:
    """基于 ripgrep（如有）或 grep -r 进行内容搜索"""
    search_path = search_path or os.getcwd()
    results = []

    # ── 尝试 ripgrep ──
    try:
        cmd = ["rg", "--line-number", "--no-heading", "--color", "never"]
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])
        if fixed_string:
            cmd.append("-F")
        else:
            cmd.append("-P")  # PCRE2 正则
        cmd.extend(["-g", "!.git/", "-g", "!node_modules/", "-g", "!__pycache__/",
                     "-g", "!.buffer/", "-g", "!venv/", "-g" "!.venv/"])
        if include_ext:
            for ext in include_ext.split(","):
                ext = ext.strip().lstrip(".")
                cmd.extend(["-g", f"*.{ext}"])
        cmd.extend([pattern, search_path])

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode not in (0, 1):  # rg 返回 1 = 无匹配
            raise RuntimeError(f"rg exited {proc.returncode}: {proc.stderr[:200]}")

        output = proc.stdout.strip()
        if output:
            for line in output.split("\n"):
                if len(results) >= max_results:
                    break
                # 格式: 路径:行号:内容
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path, lineno, content = parts[0], parts[1], parts[2]
                    if lineno.isdigit():
                        results.append({
                            "file": file_path,
                            "line": int(lineno),
                            "content": content.strip(),
                        })
                elif len(parts) == 2:
                    results.append({
                        "file": parts[0],
                        "line": 0,
                        "content": parts[1].strip(),
                    })
            return results
    except FileNotFoundError:
        pass  # rg 未安装，降级
    except (subprocess.TimeoutExpired, RuntimeError) as e:
        print(f"⚠️ rg 搜索失败，降级到 grep: {e}")
        pass

    # ── 降级：grep -r ──
    try:
        cmd = ["grep", "-rn"]
        if fixed_string:
            cmd.append("-F")
        else:
            cmd.append("-E")
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])
        cmd.append("--include=" + "*.py" if not include_ext else "")
        if include_ext:
            for ext in include_ext.split(","):
                ext = ext.strip().lstrip(".")
                cmd.append(f"--include=*.{ext}")
        cmd.extend(["--exclude-dir=.git", "--exclude-dir=node_modules",
                     "--exclude-dir=__pycache__", "--exclude-dir=.buffer",
                     "--exclude-dir=venv", "--exclude-dir=.venv"])
        cmd.extend([pattern, search_path])

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = proc.stdout.strip()
        if output:
            for line in output.split("\n"):
                if len(results) >= max_results:
                    break
                # 格式: 路径:行号:内容
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path, lineno, content = parts[0], parts[1], parts[2]
                    if lineno.isdigit():
                        results.append({
                            "file": file_path,
                            "line": int(lineno),
                            "content": content.strip(),
                        })
    except FileNotFoundError:
        return [{"error": "既未安装 ripgrep，也未找到 grep 命令"}]
    except subprocess.TimeoutExpired:
        return [{"error": "grep 搜索超时"}]
    except Exception as e:
        return [{"error": f"搜索失败: {e}"}]

    return results[:max_results]


def execute_code_search(arguments: dict, task=None) -> str:
    mode = arguments.get("mode", "glob")
    pattern = arguments.get("pattern", "")
    search_path = arguments.get("path")
    project_root = resolve_project_root(task)
    if not search_path:
        search_path = project_root
    max_results = arguments.get("max_results", 30)
    include_ext = arguments.get("include_ext")
    context_lines = arguments.get("context_lines", 2)
    fixed_string = arguments.get("fixed_string", True)

    if not pattern:
        return json.dumps({"type": "error", "content": "❌ pattern 不能为空"})

    # 路径安全校验
    try:
        validated = validate_path_optional(search_path, project_root)
        if validated:
            search_path = validated
        else:
            return json.dumps({"type": "error", "content": f"❌ 搜索路径不在项目根目录内: {search_path}"})
    except Exception as e:
        return json.dumps({"type": "error", "content": str(e)})

    if not os.path.isdir(search_path):
        return json.dumps({"type": "error", "content": f"❌ 路径不存在: {search_path}"})

    if mode == "glob":
        raw_results = _glob_search(pattern, search_path, max_results)
        if not raw_results:
            return json.dumps({"type": "text", "content": f"🔍 glob 搜索无结果: `{pattern}` in `{search_path}`"})

        lines = [f"🔍 glob 搜索结果: `{pattern}` (共 {len(raw_results)} 个文件)\n"]
        for r in raw_results:
            size_str = f"{r['size'] / 1024:.1f}KB" if r['size'] > 1024 else f"{r['size']}B"
            lines.append(f"  📄 `{r['path']}` ({size_str})")
        return json.dumps({"type": "text", "content": "\n".join(lines)}, ensure_ascii=False)

    elif mode == "grep":
        raw_results = _grep_search(pattern, search_path, max_results,
                                   include_ext, context_lines, fixed_string)

        # 检查是否有错误返回
        if raw_results and isinstance(raw_results[0], dict) and "error" in raw_results[0]:
            return json.dumps({"type": "error", "content": raw_results[0]["error"]})

        if not raw_results:
            return json.dumps({"type": "text", "content": f"🔍 grep 搜索无结果: `{pattern}` in `{search_path}`"})

        # 按文件分组
        files: dict[str, list] = {}
        for r in raw_results:
            f = r.get("file", "")
            if f not in files:
                files[f] = []
            files[f].append(r)

        lines = [f"🔍 grep 搜索结果: `{pattern}` (共 {sum(len(v) for v in files.values())} 处匹配, {len(files)} 个文件)\n"]
        for file_path, matches in files.items():
            try:
                rel = os.path.relpath(file_path, search_path)
            except ValueError:
                rel = file_path
            lines.append(f"  📄 `{rel}`:")
            for m in matches[:8]:  # 每个文件最多展示 8 行
                lines.append(f"    L{m['line']:>5d}:  {m['content'][:120]}")
            if len(matches) > 8:
                lines.append(f"    ... 还有 {len(matches) - 8} 处匹配")

        return json.dumps({"type": "text", "content": "\n".join(lines)}, ensure_ascii=False)

    return json.dumps({"type": "error", "content": "❌ 未知搜索模式"})
