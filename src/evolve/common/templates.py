"""Evolve 工厂共用的落盘动作（GOAL/GUIDE/自测脚本）。"""

import os

from .report import write_text


def write_goal(workplace_root: str, goal: str) -> None:
    if goal:
        write_text(
            os.path.join(workplace_root, "GOAL.md"),
            f"# 🎯 Build Goal\n\n{goal}\n",
            newline="\n",
        )


def write_guide(workplace_root: str, guide_text: str) -> None:
    write_text(os.path.join(workplace_root, "GUIDE.md"), guide_text, newline="\n")


def write_goal_and_guide(workplace_root: str, goal: str, guide_text: str) -> None:
    write_goal(workplace_root, goal)
    write_guide(workplace_root, guide_text)


def write_sandbox_validator(validator_module, target_path: str) -> None:
    """把 validator 模块源码原样拷贝进沙盒，供独立运行。"""
    with open(validator_module.__file__, "r", encoding="utf-8") as f:
        source = f.read()
    write_text(target_path, source, newline="\n")
