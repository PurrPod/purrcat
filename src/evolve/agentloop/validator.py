# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""AgentLoop（范式）校验器 —— 格式 / 功能 / 关键词汇 三重校验。

本文件同时承担两个角色（单一事实来源，逻辑不会漂移）：
1. 宿主侧权威校验：合并网关调用 ``validate_agentloop_file``，未全绿禁止合并；
2. 沙盒自测脚本：工厂会把本文件逐字拷贝为沙盒里的 ``evals/validate.py``，
   直接 ``uv run evals/validate.py`` 即可离线自查。

因此本文件禁止依赖任何包内相对导入，只用标准库 + pyyaml。
"""

import json
import os
import sys

try:
    import yaml
except ImportError:  # 沙盒裸 python 环境下给出可读提示
    print("缺少依赖 pyyaml，请用 `uv run evals/validate.py` 运行本脚本")
    sys.exit(2)


# ==========================================
# 专有词汇表（关键词汇校验的白名单）
# ==========================================

# hooks 的键 = 阶段名（stage）
STAGES = {
    "on_build_system_prompt",
    "on_input_received",
    "on_loop_start",
    "on_loop_epoch",
    "on_tool_calling",
    "on_loop_end",
}

# 每条 hook 的键 = 动作名（action） → 必填参数列表
ACTIONS = {
    "injection": ["content"],
    "memo_injection": [],
    "skill_info": ["skills"],
    "search": ["query"],
    "tool_use_check": ["name"],
    "keyword_check": ["keyword"],
    "file_operation": ["action"],
    "command_run": ["command"],
    "command_on": ["command"],  # 旧版命名，兼容
}

# file_operation 的 action 取值白名单
FILE_OPERATIONS = {"read", "exist_check", "write_in", "add_in", "delete"}

# file_operation 中属于「检查」的 action（write_in / add_in 是写操作，不做通过/不通过判定）
FILE_CHECK_OPS = {"read", "exist_check", "delete"}

# 宿主原生工具白名单：tool_use_check.name 只能是这些；
# 外部拓展工具（MCP）不是原生工具，须经 CallMCP 的参数检查，不能直接写进 name。
NATIVE_TOOLS = {
    "FileSystem",
    "Bash",
    "BrainStorm",
    "Cron",
    "CallMCP",
    "Memo",
    "Request",
    "Search",
    "Fetch",
    "Task",
    "KernelUpgrade",
}

# 可被 @引用 的符号（injection.content 内）
REF_ALIASES = {
    "@RULES",
    "@INFO",
    "@SOUL",
    "@MEMORY",
    "@SYS",
    "@USERQUERY",
    "@TASKSPACE",
    "@PLAN",
}

# 顶层必填字段（硬性）：缺失直接判 error
REQUIRED_TOP = ["name", "hooks"]
# 顶层建议字段（软性）：缺失只判 warn
RECOMMENDED_TOP = ["description", "description-en", "path"]


def _check(checks, title, ok, level, detail=""):
    checks.append({"title": title, "ok": bool(ok), "level": level, "detail": detail})
    return bool(ok)


def validate_agentloop_doc(doc, expected_name=None):
    """校验一个已解析的 agentloop dict，返回结构化报告。

    Returns:
        {"checks": [...], "errors": int, "warnings": int, "ok": bool}
    """
    checks = []

    # ---- 格式校验 ----
    if not isinstance(doc, dict):
        _check(
            checks, "YAML 顶层为映射对象", False, "error", "顶层必须是 key: value 映射"
        )
        return _report(checks)
    _check(checks, "YAML 顶层为映射对象", True, "error")

    for key in REQUIRED_TOP:
        if key not in doc:
            _check(
                checks,
                f"必填字段 `{key}` 存在",
                False,
                "error",
                f"缺少顶层字段 `{key}`",
            )
    for key in RECOMMENDED_TOP:
        if key not in doc:
            _check(checks, f"建议字段 `{key}` 存在", False, "warn", f"建议补齐 `{key}`")

    name = doc.get("name")
    if expected_name and name and str(name) != expected_name:
        _check(
            checks,
            "name 与文件名一致",
            False,
            "error",
            f"name={name!r}，文件名={expected_name!r}（市场安装以文件名作标识）",
        )
    elif expected_name and name:
        _check(checks, "name 与文件名一致", True, "error")

    retry = doc.get("loop_end_max_retry")
    if retry is not None and not isinstance(retry, int):
        _check(checks, "loop_end_max_retry 为整数", False, "warn", f"当前 {retry!r}")

    # ---- 关键词汇 + 功能校验（hooks）----
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        _check(
            checks, "hooks 为非空映射", False, "error", "hooks 必须是非空阶段→动作映射"
        )
        return _report(checks)
    _check(checks, "hooks 为非空映射", True, "error")

    for stage, actions in hooks.items():
        if stage not in STAGES:
            _check(
                checks,
                f"阶段 `{stage}` 属于白名单",
                False,
                "error",
                f"未知阶段，合法值：{sorted(STAGES)}",
            )
            continue
        _check(checks, f"阶段 `{stage}` 属于白名单", True, "error")

        if not isinstance(actions, list):
            _check(checks, f"`{stage}` 为动作数组", False, "error", "值必须是数组")
            continue

        for j, task in enumerate(actions):
            if not isinstance(task, dict) or len(task) != 1:
                _check(
                    checks,
                    f"`{stage}`[{j}] 为单键对象",
                    False,
                    "error",
                    "每个 hook 必须是 {action: {参数}} 的单键对象",
                )
                continue
            action = next(iter(task))
            params = task[action]
            if action not in ACTIONS:
                _check(
                    checks,
                    f"动作 `{action}` 属于白名单",
                    False,
                    "error",
                    f"未知动作，合法值：{sorted(ACTIONS)}",
                )
                continue
            _check(checks, f"动作 `{action}` 属于白名单", True, "error")

            if params is not None and not isinstance(params, dict):
                _check(
                    checks,
                    f"`{stage}`[{j}].{action} 参数为对象",
                    False,
                    "error",
                    "参数必须是映射对象",
                )
                continue
            params = params or {}

            for req in ACTIONS[action]:
                if req not in params:
                    _check(
                        checks,
                        f"动作 `{action}` 含必填参数 `{req}`",
                        False,
                        "error",
                        f"{action} 缺少参数 `{req}`",
                    )

            if action == "tool_use_check":
                tname = params.get("name")
                if isinstance(tname, str) and tname not in NATIVE_TOOLS:
                    _check(
                        checks,
                        "tool_use_check.name 属于原生工具白名单",
                        False,
                        "warn",
                        f"{tname!r} 不是宿主原生工具；外部 MCP 工具请改用 name='CallMCP' 并检查其 tool_name 参数"
                        f"（合法值：{sorted(NATIVE_TOOLS)}）",
                    )

            if action == "file_operation":
                op = params.get("action")
                if op is not None and op not in FILE_OPERATIONS:
                    _check(
                        checks,
                        "file_operation.action 属于白名单",
                        False,
                        "error",
                        f"未知 action={op!r}，合法值：{sorted(FILE_OPERATIONS)}",
                    )
                if "path" not in params:
                    _check(
                        checks,
                        "file_operation 含 `path`",
                        False,
                        "warn",
                        "缺少 path，运行时会退化到空路径",
                    )

            # 检查类动作：产出就是提示词，缺 failed_prompt 等于白写
            if _is_prompt_less_check(action, params):
                _check(
                    checks,
                    f"检查类动作 `{action}` 写了 failed_prompt",
                    False,
                    "warn",
                    f"{action} 未写 failed_prompt：检查不通过时不会有任何提示注入给模型"
                    "（挂在 on_input_received 上更是毫无效果）。"
                    "除非它只当「纯放行的闸门」用，否则请补 failed_prompt（必要时再补 successed_prompt）",
                )

            # 关键词汇：@引用 符号白名单
            for bad in _unknown_refs(params):
                _check(
                    checks,
                    f"@引用 `{bad}` 已登记",
                    False,
                    "warn",
                    f"未登记的 @符号（可能是拼写错误）：{bad}",
                )

    return _report(checks)


def _has_text(value):
    """参数是否给了非空文本。"""
    return bool(str(value or "").strip())


def _is_prompt_less_check(action, params):
    """检查类动作是否漏写了提示词（检查只有配上提示词才对模型可见）。

    - tool_use_check / keyword_check：看 failed_prompt；
    - file_operation：仅 read / exist_check / delete 属于检查，看 failed_prompt；
    - command_run / command_on：return_log 为真时会回传命令输出，此时不再要求 failed_prompt。
    """
    if action in ("tool_use_check", "keyword_check"):
        return not _has_text(params.get("failed_prompt"))
    if action == "file_operation":
        return params.get("action") in FILE_CHECK_OPS and not _has_text(
            params.get("failed_prompt")
        )
    if action in ("command_run", "command_on"):
        return not bool(params.get("return_log")) and not _has_text(
            params.get("failed_prompt")
        )
    return False


def _unknown_refs(params):
    """在参数值里扫描形如 @XXX 的引用，返回未登记符号的集合。"""
    found = set()

    def walk(v):
        if isinstance(v, str):
            for tok in v.replace("\n", " ").split():
                if tok.startswith("@"):
                    base = tok.split("/")[0].split("\\")[0].strip(",.;:，。：；")
                    if base and base not in REF_ALIASES:
                        found.add(base)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(params)
    return found


def _report(checks):
    errors = sum(1 for c in checks if c["level"] == "error" and not c["ok"])
    warnings = sum(1 for c in checks if c["level"] == "warn" and not c["ok"])
    return {"checks": checks, "errors": errors, "warnings": warnings, "ok": errors == 0}


def validate_agentloop_file(path, expected_name=None):
    """读取并校验一个 agentloop 文件，返回结构化报告。"""
    checks = []
    if not os.path.isfile(path):
        _check(checks, "文件存在", False, "error", f"未找到 {path}")
        return _report(checks)
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except Exception as e:
        _check(checks, "YAML 可解析", False, "error", f"解析失败：{e}")
        return _report(checks)
    _check(checks, "YAML 可解析", True, "error")
    res = validate_agentloop_doc(doc, expected_name)
    res["checks"] = checks + res["checks"]
    res["errors"] = sum(
        1 for c in res["checks"] if c["level"] == "error" and not c["ok"]
    )
    res["warnings"] = sum(
        1 for c in res["checks"] if c["level"] == "warn" and not c["ok"]
    )
    res["ok"] = res["errors"] == 0
    return res


def _locate_config():
    """沙盒自测用：在父目录里找唯一的 *.yaml/*.yml。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands = sorted(
        f
        for f in os.listdir(root)
        if f.endswith((".yaml", ".yml")) and not f.startswith(".")
    )
    if len(cands) >= 1:
        path = os.path.join(root, cands[0])
        return path, os.path.splitext(cands[0])[0]
    return None, None


def _print_report(title, report):
    print("=" * 56)
    print(title)
    print("=" * 56)
    for c in report["checks"]:
        if c["ok"]:
            mark = "✅"
        elif c["level"] == "error":
            mark = "❌"
        else:
            mark = "⚠️ "
        line = f"  {mark} [{c['level']}] {c['title']}"
        if not c["ok"] and c["detail"]:
            line += f" — {c['detail']}"
        print(line)
    print(
        f"\n错误 {report['errors']}，警告 {report['warnings']}，"
        f"结论：{'✅ 通过' if report['ok'] else '❌ 未通过'}"
    )
    return report["ok"]


def main():
    path, name = _locate_config()
    if not path:
        print("❌ 未在沙盒根目录找到 agentloop YAML（*.yaml/*.yml）")
        return 1
    report = validate_agentloop_file(path, expected_name=name)
    ok = _print_report(f"AgentLoop 校验：{os.path.basename(path)}", report)

    # 落盘结论，供宿主/前端读取
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "validation.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

    print(
        "\n提示：修正 ✗ 项后重跑本脚本；全绿后再用 KernelUpgrade(action='merge', type='agentloop') 申请合并。"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
