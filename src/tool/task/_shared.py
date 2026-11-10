"""Task 工具的纯校验逻辑：任务名与图参数，不触碰磁盘。"""

from __future__ import annotations

import re

INVALID_NAME_RE = re.compile(r'[\\/:*?"<>|.]')


def validate_task_name(name: str) -> str | None:
    """非法字符（路径分隔符/小数点等）会破坏落盘，返回引导文案。"""
    if INVALID_NAME_RE.search(name):
        return (
            "❌ 任务名称(name)包含非法字符。\n"
            '💡 引导建议：为了保障底层落盘和文件系统安全，任务名称不能包含斜杠、小数点及冒号等特殊字符（如 \\ / : * ? " < > | .）。请修改名称后重试！'
        )
    return None


def collect_missing_required(param_schema: dict, inputs: dict) -> list[dict]:
    return [
        {
            "name": key,
            "type": value.get("type", "any"),
            "description": value.get("description", "无描述"),
        }
        for key, value in param_schema.items()
        if value.get("required", True) and (key not in inputs or inputs[key] is None)
    ]


def collect_extra_keys(param_schema: dict, inputs: dict) -> list[str]:
    return [key for key in inputs if key not in param_schema]


def build_param_error_text(
    missing_required: list[dict], extra_keys: list[str], graph_name: str
) -> str:
    """返回参数错误提示；无错误时返回空串。"""
    validation_errors = []
    if missing_required:
        miss_str = "\n".join(
            [
                f"  - '{p['name']}' (类型: {p['type']}, 描述: {p['description']})"
                for p in missing_required
            ]
        )
        validation_errors.append(f"❌ 缺少必填参数:\n{miss_str}")

    if extra_keys:
        extra_str = ", ".join(f"'{key}'" for key in extra_keys)
        validation_errors.append(f"⚠️ 传入了未知参数: {extra_str}")

    if not validation_errors:
        return ""

    help_text = "\n".join(validation_errors)
    help_text += (
        f"\n\n💡 引导建议：你不确定参数时，请先调用 action='list_graphs' "
        f"仔细查看 '{graph_name}' 需要的 inputs 参数格式后再试！"
    )
    return help_text
