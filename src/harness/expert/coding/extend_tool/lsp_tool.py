"""
lsp_tool — 代码智能工具（基于 LSP 协议）

借鉴 Claude Code LSPTool 设计：
- go_to_definition: 跳转到定义
- find_references: 查找引用
- hover: 获取悬浮文档/类型信息
- document_symbols: 列出文件中的所有符号
- workspace_symbols: 搜索工作区符号

支持的语言：
  - Python: 使用 jedi (无需 LSP 服务器)
  - TypeScript/JS: 使用 TypeScript compiler API (fallback 到正则)
  - 通用: 正则表达式兜底
"""

import json
import os
import re
import subprocess
import ast
from pathlib import Path
from .path_utils import validate_path, resolve_project_root

LSP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lsp",
        "description": "代码智能分析。支持查找定义、引用、悬浮文档、文档符号、工作区符号搜索。帮助理解代码结构和关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["go_to_definition", "find_references", "hover", "document_symbols", "workspace_symbols"],
                    "description": "操作类型：go_to_definition(跳转定义)、find_references(查找引用)、hover(类型/文档信息)、document_symbols(文件符号列表)、workspace_symbols(工作区符号搜索)"
                },
                "file_path": {
                    "type": "string",
                    "description": "目标文件绝对路径（go_to_definition/find_references/hover/document_symbols 时需要）"
                },
                "line": {
                    "type": "integer",
                    "description": "行号（从 1 开始，go_to_definition/find_references/hover 时需要）"
                },
                "column": {
                    "type": "integer",
                    "description": "列号（从 1 开始，go_to_definition/find_references/hover 时需要）"
                },
                "symbol_name": {
                    "type": "string",
                    "description": "搜索的符号名称（workspace_symbols 时使用）"
                },
                "workspace_path": {
                    "type": "string",
                    "description": "工作区路径（workspace_symbols 时需要）"
                }
            },
            "required": ["operation"]
        }
    }
}


# ─── Python 分析（基于 ast + 启发式） ───

def _get_python_symbol_at_position(file_path: str, line: int, column: int) -> str | None:
    """获取 Python 文件中指定位置的符号名"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.split("\n")
        if line < 1 or line > len(lines):
            return None
        text_line = lines[line - 1]
        if column < 1 or column > len(text_line) + 1:
            return None
        # 提取标识符
        match = re.search(r'[a-zA-Z_][a-zA-Z0-9_.]*', text_line[column - 1:])
        if match:
            return match.group()
        return None
    except Exception:
        return None


def _get_class_func_at_line(file_path: str, line: int) -> list[dict]:
    """获取 Python 文件中某行所在的所有类和函数上下文"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=file_path)
        results = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, 'lineno') and node.lineno <= line <= (getattr(node, 'end_lineno', node.lineno) or node.lineno):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    results.append({
                        "kind": kind,
                        "name": node.name,
                        "line": node.lineno,
                    })
        return results
    except SyntaxError:
        return []
    except Exception:
        return []


def _parse_python_symbols(file_path: str) -> list[dict]:
    """解析 Python 文件中的符号"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=file_path)
        symbols = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append({
                    "kind": "class",
                    "name": node.name,
                    "line": node.lineno,
                    "doc": ast.get_docstring(node) or "",
                })
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append({
                            "kind": "method",
                            "name": f"{node.name}.{item.name}",
                            "line": item.lineno,
                            "doc": ast.get_docstring(item) or "",
                        })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({
                    "kind": "function",
                    "name": node.name,
                    "line": node.lineno,
                    "doc": ast.get_docstring(node) or "",
                })

        return symbols
    except SyntaxError:
        return []
    except Exception:
        return []


def _go_to_definition_python(file_path: str, line: int, column: int) -> str:
    """Python 定义跳转（基于启发式）"""
    symbol = _get_python_symbol_at_position(file_path, line, column)
    if not symbol:
        return "❌ 无法识别当前位置的符号"

    # 尝试导入分析：搜索项目内的定义
    base_dir = os.path.dirname(file_path)
    parts = symbol.split(".")
    search_name = parts[0] if parts else symbol

    for root, dirs, files in os.walk(base_dir):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            if not f.endswith(".py"):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                tree = ast.parse(content, filename=fpath)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name == search_name:
                            rel = os.path.relpath(fpath, base_dir)
                            return f"✅ 找到定义: `{symbol}`\n   📄 `{rel}` 第 {node.lineno} 行"
            except (SyntaxError, UnicodeDecodeError):
                continue

    # 搜索引用的模块
    import_match = re.search(r'from\s+([.\w]+)\s+import\s+.*\b' + re.escape(search_name) + r'\b', 
                             open(file_path).read())
    if import_match:
        return f"⚠️ `{symbol}` 可能从 `{import_match.group(1)}` 导入，但未在本项目找到定义"

    return f"⚠️ 未找到 `{symbol}` 的定义（可能来自第三方库）"


def _find_references_python(file_path: str, line: int, column: int) -> str:
    """Python 查找引用"""
    symbol = _get_python_symbol_at_position(file_path, line, column)
    if not symbol:
        return "❌ 无法识别当前位置的符号"

    base_dir = os.path.dirname(file_path)
    results = []

    for root, dirs, files in os.walk(base_dir):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            if not f.endswith(".py"):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    for i, text_line in enumerate(fh, 1):
                        if symbol in text_line:
                            rel = os.path.relpath(fpath, base_dir)
                            results.append(f"  📄 `{rel}` L{i:>5d}: {text_line.strip()[:100]}")
            except (UnicodeDecodeError, OSError):
                continue

    if not results:
        return f"🔍 未找到 `{symbol}` 的引用"
    
    return f"🔍 找到 {len(results)} 处 `{symbol}` 的引用:\n" + "\n".join(results[:20])


def _hover_python(file_path: str, line: int, column: int) -> str:
    """Python 获取类型/文档信息"""
    context = _get_class_func_at_line(file_path, line)
    symbol = _get_python_symbol_at_position(file_path, line, column)

    parts = []
    if context:
        for c in context:
            parts.append(f"  {c['kind']}: `{c['name']}` (L{c['line']})")

    if symbol:
        parts.append(f"\n符号: `{symbol}`")

    if not parts:
        return "📍 当前位置: 第 {line} 行"

    return "📝 **上下文信息**\n" + "\n".join(parts)


# ─── 通用 / 正则兜底 ───

def _parse_symbols_regex(file_path: str) -> list[dict]:
    """基于正则的符号提取（通用）"""
    ext = Path(file_path).suffix.lower()
    symbols = []

    patterns = {
        ".py": [
            (r'^class\s+(\w+)', "class"),
            (r'^async?\s+def\s+(\w+)', "function"),
            (r'^\s+def\s+(\w+)', "method"),
        ],
        ".ts": [
            (r'(?:export\s+)?(?:default\s+)?class\s+(\w+)', "class"),
            (r'(?:export\s+)?(?:default\s+)?function\s+(\w+)', "function"),
            (r'(?:export\s+)?interface\s+(\w+)', "interface"),
            (r'(?:export\s+)?type\s+(\w+)\s*=', "type"),
            (r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', "function"),
            (r'(?:export\s+)?default\s+function\s+(\w+)', "function"),
            (r'const\s+(\w+)\s*[:=]', "variable"),
        ],
        ".js": [
            (r'class\s+(\w+)', "class"),
            (r'function\s+(\w+)', "function"),
            (r'(?:export\s+)?default\s+function\s+(\w+)', "function"),
            (r'const\s+(\w+)\s*=', "variable"),
        ],
        ".go": [
            (r'func\s+(\w+)', "function"),
            (r'type\s+(\w+)\s+struct', "struct"),
            (r'type\s+(\w+)\s+interface', "interface"),
        ],
        ".rs": [
            (r'fn\s+(\w+)', "function"),
            (r'struct\s+(\w+)', "struct"),
            (r'enum\s+(\w+)', "enum"),
            (r'trait\s+(\w+)', "trait"),
        ],
        ".java": [
            (r'(?:public|private|protected)?\s*(?:static)?\s*(?:final)?\s*(?:class|interface)\s+(\w+)', "class"),
            (r'(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(', "method"),
        ],
    }

    file_patterns = patterns.get(ext, [])
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        for pattern, kind in file_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_no = content[:match.start()].count("\n") + 1
                symbols.append({
                    "kind": kind,
                    "name": match.group(1),
                    "line": line_no,
                })
    except Exception:
        pass

    return symbols


# ─── 主入口 ───

def execute_lsp(arguments: dict, task=None) -> str:
    operation = arguments.get("operation", "")
    file_path = arguments.get("file_path", "")
    line = arguments.get("line", 1)
    column = arguments.get("column", 1)
    symbol_name = arguments.get("symbol_name", "")
    project_root = resolve_project_root(task)
    workspace_path = arguments.get("workspace_path", project_root)

    if not operation:
        return json.dumps({"type": "error", "content": "❌ operation 不能为空"})

    # 如果涉及文件路径，校验安全
    if file_path:
        try:
            file_path = validate_path(file_path, project_root)
        except ValueError as e:
            return json.dumps({"type": "error", "content": str(e)})

    # ── document_symbols：文件符号列表 ──
    if operation == "document_symbols":
        if not file_path or not os.path.isfile(file_path):
            return json.dumps({"type": "error", "content": "❌ 文件不存在"})

        ext = Path(file_path).suffix.lower()
        if ext == ".py":
            symbols = _parse_python_symbols(file_path)
        else:
            symbols = _parse_symbols_regex(file_path)

        if not symbols:
            return json.dumps({"type": "text", "content": f"📄 `{file_path}` 中未找到符号"})

        lines = [f"📄 符号列表: `{file_path}` ({len(symbols)} 个符号)\n"]
        for s in symbols:
            doc = s.get("doc", "")
            doc_snippet = f" — {doc[:60]}" if doc else ""
            lines.append(f"  {s['kind']:12s} `{s['name']}`  L{s['line']}{doc_snippet}")

        return json.dumps({"type": "text", "content": "\n".join(lines)}, ensure_ascii=False)

    # ── workspace_symbols：工作区符号搜索 ──
    elif operation == "workspace_symbols":
        if not symbol_name:
            return json.dumps({"type": "error", "content": "❌ symbol_name 不能为空"})
        try:
            workspace_path = validate_path(workspace_path, project_root)
        except ValueError as e:
            return json.dumps({"type": "error", "content": str(e)})

        results = []
        for root, dirs, files in os.walk(workspace_path):
            if ".git" in dirs:
                dirs.remove(".git")
            for f in files:
                if not f.endswith((".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java")):
                    continue
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        for i, text_line in enumerate(fh, 1):
                            if re.search(r'(class|def|function|fn|func|interface|type|struct|enum)\s+' + re.escape(symbol_name) + r'\b', text_line):
                                rel = os.path.relpath(fpath, workspace_path)
                                results.append(f"  📄 `{rel}` L{i:>5d}: {text_line.strip()[:100]}")
                                break
                except (UnicodeDecodeError, OSError):
                    continue
                if len(results) >= 20:
                    break
            if len(results) >= 20:
                break

        if not results:
            return json.dumps({"type": "text", "content": f"🔍 未找到符号 `{symbol_name}`"})

        return json.dumps({"type": "text", "content": f"🔍 符号 `{symbol_name}` 定义位置:\n" + "\n".join(results)}, ensure_ascii=False)

    # ── 需要文件路径的操作 ──
    if not file_path or not os.path.isfile(file_path):
        return json.dumps({"type": "error", "content": "❌ 文件不存在"})

    ext = Path(file_path).suffix.lower()

    # ── go_to_definition ──
    if operation == "go_to_definition":
        if ext == ".py":
            result = _go_to_definition_python(file_path, line, column)
        else:
            result = f"⚠️ 不支持 {ext} 文件的定义跳转（可使用 code_search grep 搜索符号 `{_get_python_symbol_at_position(file_path, line, column) or ''}`）"
        return json.dumps({"type": "text", "content": result}, ensure_ascii=False)

    # ── find_references ──
    elif operation == "find_references":
        if ext == ".py":
            result = _find_references_python(file_path, line, column)
        else:
            symbol = _get_python_symbol_at_position(file_path, line, column) or "symbol"
            result = f"⚠️ 使用 grep 搜索 `{symbol}` 的引用:\n"
            # fallback to grep
            try:
                grep = subprocess.run(
                    ["grep", "-rn", symbol, os.path.dirname(file_path)],
                    capture_output=True, text=True, timeout=30
                )
                if grep.stdout:
                    for line_item in grep.stdout.split("\n")[:20]:
                        result += f"  {line_item}\n"
                else:
                    result += "  未找到引用"
            except Exception:
                result += "  搜索失败"
        return json.dumps({"type": "text", "content": result}, ensure_ascii=False)

    # ── hover ──
    elif operation == "hover":
        if ext == ".py":
            result = _hover_python(file_path, line, column)
        else:
            result = f"📍 第 {line} 行（{ext} 文件）"
        return json.dumps({"type": "text", "content": result}, ensure_ascii=False)

    return json.dumps({"type": "error", "content": f"❌ 未知操作: {operation}"})
