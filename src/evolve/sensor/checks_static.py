"""Sensor L0 静态契约检查（SPEC-020）。

只做脚本文本分析：PEP 723 / stdout 重定向 / 强制退出 / 硬编码密钥 /
配置结构与 env 声明交叉校验。检查项顺序与文案是报告契约的一部分。
"""

import re

_ENV_PAT = re.compile(
    r"""os\.environ(?:\.get\(|\[)\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""
    r"""|os\.getenv\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""
)
_SECRET_PAT = re.compile(
    r"(?i)\b(token|secret|password|passwd|api_?key|app_?secret|access_?key)\b"
    r"\s*[:=]\s*['\"][A-Za-z0-9_\-\.\+/]{16,}['\"]"
)
_EXIT_PAT = re.compile(r"\b(?:sys\.exit|os\._exit)\s*\(")


def static_checks(
    script_text: str, config: dict, config_error: str, sensor_name: str
) -> list:
    cases = []

    def add(case_id, title, passed, detail, level="error"):
        cases.append(
            {
                "id": case_id,
                "layer": "L0",
                "title": title,
                "pass": bool(passed),
                "detail": detail,
                "level": level,
            }
        )

    # 1. PEP 723 内联依赖
    has_pep723 = "# /// script" in script_text and script_text.count("# ///") >= 2
    add(
        "pep723",
        "PEP 723 内联依赖声明",
        has_pep723,
        "已声明内联依赖块"
        if has_pep723
        else "缺少 `# /// script` 内联依赖块，uv run 无法建环境",
    )

    # 2. stdout 重定向（协议通道纯净的前提）
    has_redirect = bool(
        re.search(r"sys\.stdout\s*=\s*sys\.stderr", script_text)
        or re.search(r"_REAL_STDOUT\s*=\s*sys\.stdout", script_text)
    )
    add(
        "stdout_redirect",
        "stdout 重定向到 stderr",
        has_redirect,
        "日志已改道 stderr，协议通道独占 stdout"
        if has_redirect
        else "未见 `sys.stdout = sys.stderr`，print 日志会污染协议通道",
    )

    # 3. 无强制退出
    exit_hit = _EXIT_PAT.search(script_text)
    add(
        "no_force_exit",
        "无强制退出调用",
        not exit_hit,
        "未发现 sys.exit / os._exit"
        if not exit_hit
        else f"发现强制退出调用 `{exit_hit.group(0)}`，违反「严禁退出主进程」铁律",
    )

    # 4. 无硬编码密钥
    secret_hit = _SECRET_PAT.search(script_text)
    add(
        "no_hardcoded_secret",
        "无硬编码密钥",
        not secret_hit,
        "未发现疑似硬编码密钥"
        if not secret_hit
        else f"疑似硬编码密钥: `{secret_hit.group(0)[:60]}...`",
    )

    # 5. sensor_config.json 合法性
    if config_error:
        add("config_valid", "sensor_config.json 可解析", False, config_error)
        declared = []
    else:
        name_ok = config.get("name") == sensor_name
        env_ok = isinstance(config.get("env", {}), dict)
        add(
            "config_valid",
            "sensor_config.json 结构合法",
            name_ok and env_ok,
            f"name={config.get('name')!r}（应为 {sensor_name!r}），env 为对象={env_ok}",
        )
        declared = sorted(config.get("env", {}).keys()) if env_ok else []

    # 6. env 声明交叉校验：代码读了但没声明 —— 合并后用户无从配置
    code_keys = set()
    for match in _ENV_PAT.finditer(script_text):
        code_keys.add(match.group(1) or match.group(2))
    missing = sorted(code_keys - set(declared))
    undeclared_used = [k for k in missing if k not in {"PATH", "HOME", "TMPDIR"}]
    add(
        "env_declared",
        "代码读取的环境变量已全部声明",
        not undeclared_used,
        "代码与 sensor_config.json 的 env 键集一致"
        if not undeclared_used
        else f"代码读取了未声明的环境变量：{', '.join(undeclared_used)}，"
        "合并后用户无法在配置中心填写",
    )
    unused = sorted(set(declared) - code_keys)
    if unused:
        add(
            "env_unused",
            "声明的环境变量确实被使用",
            False,
            f"sensor_config.json 声明了但代码未读取：{', '.join(unused)}",
            level="warn",
        )

    return cases
