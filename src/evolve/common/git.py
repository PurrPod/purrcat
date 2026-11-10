"""Evolve 工厂的 Git 初始化与提交。"""

import os
import subprocess

from .report import write_text


def ensure_git_repo(
    root: str, gitignore_text: str, capture: bool = False, create: bool = False
) -> None:
    """目录尚无 .git 时初始化仓库并登记 .gitignore。"""
    if os.path.exists(os.path.join(root, ".git")):
        return
    if create:
        os.makedirs(root, exist_ok=True)
    subprocess.run(["git", "init"], cwd=root, capture_output=capture)
    write_text(os.path.join(root, ".gitignore"), gitignore_text)
    subprocess.run(["git", "add", ".gitignore"], cwd=root, capture_output=capture)


def commit_paths(root: str, paths: list, message: str, capture: bool = False) -> None:
    for path in paths:
        subprocess.run(["git", "add", path], cwd=root, capture_output=capture)
    subprocess.run(["git", "commit", "-m", message], cwd=root, capture_output=capture)
