"""PurrCat desktop 命令 — 源码模式启动 / 更新 Electron 桌面端"""

import os
import shutil
import subprocess
import sys


def _get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run(command, cwd=None, check=True):
    """前台执行命令（输出直接透传终端），返回是否成功"""
    print(f"$ {command}")
    result = subprocess.run(command, shell=True, cwd=cwd or _get_project_root())
    ok = result.returncode == 0
    if check and not ok:
        sys.exit(result.returncode)
    return ok


def _output(command, cwd=None, timeout=15):
    """静默执行命令并返回 stdout 去空白结果（失败/超时返回 None）"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd or _get_project_root(),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _check_for_updates(root):
    """非阻塞探测远端新提交，仅提示不强制"""
    if _output("git fetch --quiet", cwd=root, timeout=20) is None:
        return
    count = _output("git rev-list --count HEAD..@{u}", cwd=root, timeout=10)
    try:
        count = int(count or "0")
    except ValueError:
        return
    if count > 0:
        print(f"[*] 检测到远端 {count} 个新提交，可运行 purrcat desktop update 更新")


def cmd_start():
    root = _get_project_root()
    print("=== PurrCat Desktop Start ===")

    if not shutil.which("npm"):
        print("[x] 未检测到 npm，请先安装 Node.js 18+ : https://nodejs.org/")
        sys.exit(1)

    # 懒安装依赖：首次启动（或依赖被清理后）自动补齐
    if not os.path.isdir(os.path.join(root, "node_modules")):
        print("[*] 首次启动，安装桌面端依赖 (npm install)...")
        _run("npm install", cwd=root)
    if not os.path.isdir(os.path.join(root, "ui", "node_modules")):
        print("[*] 首次启动，安装前端依赖 (npm install --prefix ui)...")
        _run("npm install --prefix ui", cwd=root)

    _check_for_updates(root)

    print("$ npm run dev")
    print("[*] 启动中（backend + vite + electron），按 Ctrl+C 退出...")
    sys.exit(subprocess.run("npm run dev", shell=True, cwd=root).returncode)


def cmd_update():
    root = _get_project_root()
    print("=== PurrCat Desktop Update ===")

    if not shutil.which("git"):
        print("[x] 未检测到 git，请先安装 Git : https://git-scm.com/downloads")
        sys.exit(1)

    # 本地有修改时中止，避免 pull 冲突
    if _output("git status --porcelain", cwd=root):
        print("[x] 本地源码有未提交修改，已中止更新以免冲突。")
        print("    处理方式：")
        print(f"      cd {root}")
        print("      git stash   # 暂存本地修改")
        print("      purrcat desktop update")
        print("      git stash pop   # 恢复本地修改")
        sys.exit(1)

    _run("git pull --ff-only", cwd=root)
    _run("uv sync", cwd=root)
    _run("npm install", cwd=root)
    _run("npm install --prefix ui", cwd=root)

    print("")
    print("[+] 更新完成! 运行 purrcat desktop start 启动。")


def cmd_help():
    print("Usage: purrcat desktop <command>")
    print("")
    print("Commands:")
    print("  start   - Start the Electron desktop app (source mode)")
    print("  update  - Pull latest source and refresh dependencies")


def run(args):
    """desktop 子命令入口（由 scripts.cli.main 分发）"""
    sub = args[0] if args else "help"
    if sub == "start":
        cmd_start()
    elif sub == "update":
        cmd_update()
    else:
        cmd_help()
        if sub != "help":
            sys.exit(1)
