import os
import ast
import json
import subprocess
import yaml

def run_code_check(file_path: str) -> str:
    """根据文件后缀执行对应的语法和静态检查，一切正常时返回空字符串"""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".py":
        return _check_python(file_path)
    elif ext == ".json":
        return _check_json(file_path)
    elif ext in [".yaml", ".yml"]:
        return _check_yaml(file_path)
    elif ext in [".js", ".ts", ".jsx", ".tsx", ".css"]:
        return _check_frontend(file_path)
    elif ext in [".sh", ".bash"]:
        return _check_shell(file_path)
        
    return ""

def _check_python(file_path: str) -> str:
    messages = []
    
    # 1. 致命错误拦截：基础语法树检查 (AST)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            ast.parse(f.read())
        # 成功时不添加任何提示
    except SyntaxError as e:
        return f"❌ Python 致命语法错误 (SyntaxError): {e.msg} at line {e.lineno}, offset {e.offset}"
    except Exception as e:
        return f"❌ Python 文件解析失败: {str(e)}"
        
    # 2. 静态分析：调用 ruff
    try:
        result = subprocess.run(
            ["ruff", "check", file_path],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            messages.append(f"⚠️ Ruff 发现问题:\n{result.stdout.strip()}")
        # 成功时不添加任何提示
    except FileNotFoundError:
        messages.append("⚠️ 宿主机未安装 ruff，已跳过深度静态检查 (仅完成基础语法检查)")
    except subprocess.TimeoutExpired:
        messages.append("⚠️ Ruff 检查超时，已跳过")
        
    # 如果 messages 为空（即一切正常），join 后会返回空字符串
    return "\n".join(messages).strip()

def _check_json(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            json.load(f)
        return ""  # 成功时返回空
    except json.JSONDecodeError as e:
        return f"❌ JSON 格式错误: {str(e)}"

def _check_yaml(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
        return ""  # 成功时返回空
    except yaml.YAMLError as e:
        return f"❌ YAML 格式错误:\n{str(e)}"

def _check_frontend(file_path: str) -> str:
    """使用 Biome 检查前端代码 (JS/TS/CSS)"""
    try:
        result = subprocess.run(
            ["biome", "check", file_path],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            error_output = result.stderr.strip() or result.stdout.strip()
            return f"⚠️ Biome (前端) 发现问题:\n{error_output}"
        return ""  # 成功时返回空
    except FileNotFoundError:
        return "⚠️ 宿主机未安装 biome，已跳过前端代码检查。提示：如需开启检查，请在宿主机运行 `npm install -g @biomejs/biome`"
    except subprocess.TimeoutExpired:
        return "⚠️ Biome 检查超时，已跳过"

def _check_shell(file_path: str) -> str:
    """使用 shellcheck 检查 bash 脚本"""
    try:
        result = subprocess.run(
            ["shellcheck", file_path],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return f"⚠️ ShellCheck 发现问题:\n{result.stdout.strip()}"
        return ""  # 成功时返回空
    except FileNotFoundError:
        return "⚠️ 宿主机未安装 shellcheck，已跳过 Shell 脚本检查。"
    except subprocess.TimeoutExpired:
        return "⚠️ ShellCheck 检查超时，已跳过"