import os
import re
import ast
import json
import shutil
import subprocess
import yaml

from src.utils.config import get_enriched_env

# 兜底剥离 ANSI 转义序列（CSI 颜色码如 ESC[1m、OSC 8 超链接如 ESC]8;;url ESC\），
# 防止检查器输出直接进入工具结果后前端显示为乱码
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;:?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)


def _check_env() -> dict:
    """检查器子进程专用环境：合并注册表最新 PATH + 强制关闭彩色输出。

    PATH 用 get_enriched_env() 而非 os.environ：后端常驻进程的 PATH 是启动时
    的快照，用户中途 npm install -g 装的检查器（如 biome）在旧 PATH 里找不到，
    需从 HKCU/HKLM 注册表合并最新 PATH。

    颜色方面：后端从 npm/Electron 启动链继承 FORCE_COLOR=1 时，ruff 即使输出
    被管道捕获也会输出颜色码和超链接转义序列；且 ruff 0.15 对 FORCE_COLOR 是
    "存在即生效"（值为 0 也算开启），所以必须整个删除而不是置 0。
    """
    env = get_enriched_env()
    env.update({"NO_COLOR": "1", "CLICOLOR": "0"})
    for key in ("FORCE_COLOR", "CLICOLOR_FORCE"):
        env.pop(key, None)
    return env


def _run_tool(cmd: list, timeout: int = 5) -> subprocess.CompletedProcess:
    """运行检查器子进程。

    npm 全局包在 Windows 上是 .cmd shim（如 biome.CMD），CreateProcess 对无
    扩展名只自动补 .exe、不会尝试 .cmd，直接 subprocess.run(["biome", ...])
    必然 FileNotFoundError。必须先用 shutil.which 按 PATHEXT 解析完整路径。
    """
    env = _check_env()
    exe = shutil.which(cmd[0], path=env.get("PATH"))
    if exe is None:
        raise FileNotFoundError(cmd[0])
    return subprocess.run(
        [exe] + cmd[1:], capture_output=True, text=True, timeout=timeout, env=env
    )


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


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


# 诊断行形如 "src/foo.py:12:5: ..."（ruff）或 "a.sh:3:1: warning ..."（shellcheck）
# 或 "a.js:1:1 lint/xxx"（biome），统一按 "路径:行号(:列号)" 前缀识别
_DIAG_LINE_RE = re.compile(r"^[^\s:]+:\d+(?::\d+)?")


def count_code_check_issues(report: str) -> int:
    """统计检查报告中的问题条数（供工具返回简短提示用，不展开报告内容）"""
    if not report:
        return 0
    lines = [line.strip() for line in report.splitlines() if line.strip()]
    diag_lines = [line for line in lines if _DIAG_LINE_RE.match(line)]
    # 无法解析出诊断行时（如语法错误/未安装检查器），整条报告记为一条问题
    return len(diag_lines) if diag_lines else len(lines)


def _check_python(file_path: str) -> str:
    messages = []

    # 1. 致命错误拦截：基础语法树检查 (AST)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            ast.parse(f.read())
        # 成功时不添加任何提示
    except SyntaxError as e:
        return f"Python 致命语法错误 (SyntaxError): {e.msg} at line {e.lineno}, offset {e.offset}"
    except Exception as e:
        return f"Python 文件解析失败: {str(e)}"

    # 2. 静态分析：调用 ruff
    try:
        result = _run_tool(["ruff", "check", file_path])
        if result.returncode != 0:
            messages.append(f"Ruff 发现问题:\n{_strip_ansi(result.stdout).strip()}")
        # 成功时不添加任何提示
    except FileNotFoundError:
        messages.append("宿主机未安装 ruff，已跳过深度静态检查 (仅完成基础语法检查)")
    except subprocess.TimeoutExpired:
        messages.append("Ruff 检查超时，已跳过")

    # 如果 messages 为空（即一切正常），join 后会返回空字符串
    return "\n".join(messages).strip()


def _check_json(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            json.load(f)
        return ""  # 成功时返回空
    except json.JSONDecodeError as e:
        return f"JSON 格式错误: {str(e)}"


def _check_yaml(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
        return ""  # 成功时返回空
    except yaml.YAMLError as e:
        return f"YAML 格式错误:\n{str(e)}"


def _check_frontend(file_path: str) -> str:
    """使用 Biome 检查前端代码 (JS/TS/CSS)"""
    try:
        result = _run_tool(["biome", "check", file_path])
        if result.returncode != 0:
            error_output = (
                _strip_ansi(result.stderr).strip() or _strip_ansi(result.stdout).strip()
            )
            return f"Biome (前端) 发现问题:\n{error_output}"
        return ""  # 成功时返回空
    except FileNotFoundError:
        return "宿主机未安装 biome，已跳过前端代码检查。提示：如需开启检查，请在宿主机运行 `npm install -g @biomejs/biome`"
    except subprocess.TimeoutExpired:
        return "Biome 检查超时，已跳过"


def _check_shell(file_path: str) -> str:
    """使用 shellcheck 检查 bash 脚本"""
    try:
        result = _run_tool(["shellcheck", file_path])
        if result.returncode != 0:
            return f"ShellCheck 发现问题:\n{_strip_ansi(result.stdout).strip()}"
        return ""  # 成功时返回空
    except FileNotFoundError:
        return "宿主机未安装 shellcheck，已跳过 Shell 脚本检查。"
    except subprocess.TimeoutExpired:
        return "ShellCheck 检查超时，已跳过"
