"""红线静态检查：把 AGENTS.md 中可自动化的约束变成失败即拦截的用例。"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ELECTRON_DIR = "electron"
HOST_SRC_DIR = Path("ui") / "web-minimal" / "src" / "host"
PENDING_MARKERS = {"skip", "xfail"}
TASK_ID_RE = re.compile(r"(?:#\d+|[A-Z][A-Z0-9]+-\d+)")
MAX_PENDING_SKIPS = 5


def test_electron_keeps_context_isolation_and_disables_node_integration(repo_root):
    main_js = (repo_root / ELECTRON_DIR / "main.js").read_text(encoding="utf-8")
    preload_js = (repo_root / ELECTRON_DIR / "preload.js").read_text(encoding="utf-8")

    assert not re.search(r"nodeIntegration\s*:\s*true", main_js)
    assert not re.search(r"contextIsolation\s*:\s*false", main_js)
    assert "contextBridge.exposeInMainWorld" in preload_js


def test_electron_windows_use_preload_script(repo_root):
    main_js = (repo_root / ELECTRON_DIR / "main.js").read_text(encoding="utf-8")

    browser_windows = re.findall(r"webPreferences\s*:\s*\{", main_js)
    assert browser_windows, "main.js 中未找到 webPreferences"
    assert main_js.count("preload: path.join(__dirname, 'preload.js')") >= 1


def test_host_sources_do_not_bypass_typecheck(repo_root):
    offenders = []
    for path in sorted((repo_root / HOST_SRC_DIR).rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        for directive in ("@ts-ignore", "@ts-nocheck", "@ts-expect-error"):
            if directive in text:
                offenders.append(f"{path.relative_to(repo_root)}: {directive}")

    assert not offenders, "宿主 TS 禁止绕过类型检查：\n" + "\n".join(offenders)


def test_api_docs_match_real_routes(repo_root):
    result = subprocess.run(
        [sys.executable, "scripts/check_api_docs.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"API 文档与路由不一致，请更新 docs/api：\n{result.stdout}\n{result.stderr}"
    )


def test_agent_entrypoints_do_not_hardcode_secrets(repo_root):
    pattern = re.compile(r"(sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY)")
    offenders = []
    for path in sorted((repo_root / "src").rglob("*.py")):
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(repo_root)))

    assert not offenders, "疑似硬编码密钥：\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "required_path",
    ["AGENTS.md", "docs/api/README.md", "tests/specs/_TEMPLATE.md"],
)
def test_project_guardrails_exist(repo_root, required_path):
    assert (repo_root / required_path).is_file()


def _pending_skips(repo_root: Path) -> list[tuple[str, int, str, str]]:
    """收集无条件的 skip/xfail；skipif 属于环境分支，不在此列。"""
    rows = []
    for path in sorted((repo_root / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            for decorator in node.decorator_list:
                target = (
                    decorator.func if isinstance(decorator, ast.Call) else decorator
                )
                if not isinstance(target, ast.Attribute):
                    continue
                if target.attr not in PENDING_MARKERS:
                    continue
                owner = target.value
                if not (isinstance(owner, ast.Attribute) and owner.attr == "mark"):
                    continue
                reason = ""
                if isinstance(decorator, ast.Call):
                    for keyword in decorator.keywords:
                        if keyword.arg == "reason" and isinstance(
                            keyword.value, ast.Constant
                        ):
                            reason = str(keyword.value.value)
                rows.append(
                    (
                        str(path.relative_to(repo_root)),
                        node.lineno,
                        target.attr,
                        reason,
                    )
                )
    return rows


def test_pending_tests_reference_a_task(repo_root):
    offenders = [
        f"{path}:{line} {mark} reason={reason!r}"
        for path, line, mark, reason in _pending_skips(repo_root)
        if not TASK_ID_RE.search(reason)
    ]

    assert not offenders, (
        "skip/xfail 必须带 reason= 且包含任务编号（如 #123 或 TASK-123）：\n"
        + "\n".join(offenders)
    )


def test_pending_tests_stay_under_budget(repo_root):
    pending = _pending_skips(repo_root)

    assert len(pending) <= MAX_PENDING_SKIPS, (
        f"挂起用例 {len(pending)} 个，超过上限 {MAX_PENDING_SKIPS}；请修复或删除：\n"
        + "\n".join(f"{path}:{line} {mark}" for path, line, mark, _ in pending)
    )
