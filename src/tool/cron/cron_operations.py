"""Cron 闹钟核心操作模块"""

import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List

from src.tool.cron.exceptions import (
    CronNotFoundError,
    InvalidRepeatRuleError,
    InvalidTimeFormatError,
)
from src.utils.config import CRON_FILE

# 【修复】全局锁，保护 JSON 文件的并发读写
CRON_LOCK = threading.Lock()

VALID_REPEAT_RULES = [
    "none",
    "everyday",
    "weekly_1",
    "weekly_2",
    "weekly_3",
    "weekly_4",
    "weekly_5",
    "weekly_6",
    "weekly_7",
]


def _ensure_file(filepath: str):
    """确保文件存在，不存在则创建空列表"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump([], f)


def _read_json(filepath: str) -> List[Dict[str, Any]]:
    """读取 JSON 文件内容"""
    _ensure_file(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(filepath: str, data: List[Dict[str, Any]]):
    """原子写入 JSON 文件

    System Clock 是独立进程，会同时读写 cron.json。直接 `open(..., "w")`
    会让对方在写入途中读到半截 JSON；用 tmp + os.replace 保证读者只能看到
    完整的旧版本或完整的新版本。
    """
    tmp = f"{filepath}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)


def _validate_time_format(time_str: str) -> bool:
    """验证时间格式是否为 HH:MM"""
    import re

    return bool(re.match(r"^([01]\d|2[0-3]):[0-5]\d$", time_str))


def _validate_repeat_rule(rule: str) -> bool:
    """验证重复规则是否有效"""
    return rule in VALID_REPEAT_RULES


def _find_cron_index(crons: List[Dict[str, Any]], identifier: str) -> int:
    """根据 id 或 title 查找闹钟的索引，优先精确匹配 id"""
    for i, cron in enumerate(crons):
        if cron["id"] == identifier:
            return i
    for i, cron in enumerate(crons):
        if cron["title"] == identifier:
            return i
    return -1


def add_cron(
    title: str,
    trigger_time: str,
    repeat_rule: str = "none",
    description: str = "",
    task_hook: str = "Agent",
    task_inputs: dict = None,
) -> dict:
    """
    添加闹钟

    Args:
        title: 闹钟标题
        trigger_time: 触发时间，HH:MM 格式（如 08:30）
        repeat_rule: 重复规则，默认 "none"
        description: 闹钟详细描述，默认空字符串
        task_hook: 任务钩子，默认 "Agent"
        task_inputs: 工作流入参，默认空字典

    Returns:
        包含 id, title, description, trigger_time, repeat_rule, active 的字典
    """
    if not _validate_time_format(trigger_time):
        raise InvalidTimeFormatError(trigger_time)

    if not _validate_repeat_rule(repeat_rule):
        raise InvalidRepeatRuleError(repeat_rule)

    with CRON_LOCK:
        crons = _read_json(CRON_FILE)
        cron_id = "crn_" + str(uuid.uuid4())[:8]

        item = {
            "id": cron_id,
            "title": title,
            "description": description,
            "trigger_time": trigger_time,
            "repeat_rule": repeat_rule,
            "active": True,
            # 武装时刻：一次性闹钟的"预定场次"从这里算起，
            # 而不是每次进程启动时重新理解为"下一次 HH:MM"
            "armed_at": datetime.now().isoformat(timespec="seconds"),
            "last_fired_at": None,
            "task_hook": task_hook,  # 🌟 默认绑定为唤醒 Agent
            "task_inputs": task_inputs or {},  # 🌟 若有工作流入参则附带
        }

        crons.append(item)
        _write_json(CRON_FILE, crons)

    return item


def delete_cron(identifier: str) -> dict:
    """删除闹钟 (支持传入 ID 或 Name)"""
    with CRON_LOCK:
        crons = _read_json(CRON_FILE)
        idx = _find_cron_index(crons, identifier)

        if idx == -1:
            raise CronNotFoundError(identifier)

        deleted = crons.pop(idx)
        _write_json(CRON_FILE, crons)
    return {"message": f"闹钟 '{deleted['title']}' ({deleted['id']}) 删除成功"}


def update_cron(
    identifier: str,
    trigger_time: str = None,
    repeat_rule: str = None,
    active: bool = None,
    description: str = None,
) -> dict:
    """修改闹钟 (支持传入 ID 或 Name，不再支持修改 title)"""
    with CRON_LOCK:
        crons = _read_json(CRON_FILE)
        idx = _find_cron_index(crons, identifier)

        if idx == -1:
            raise CronNotFoundError(identifier)

        cron = crons[idx]
        now_iso = datetime.now().isoformat(timespec="seconds")
        rearmed = False

        if trigger_time is not None:
            if not _validate_time_format(trigger_time):
                raise InvalidTimeFormatError(trigger_time)
            cron["trigger_time"] = trigger_time
            rearmed = True

        if repeat_rule is not None:
            if not _validate_repeat_rule(repeat_rule):
                raise InvalidRepeatRuleError(repeat_rule)
            cron["repeat_rule"] = repeat_rule
            rearmed = True

        if active is not None:
            cron["active"] = active
            # 重新启用一次性闹钟时重新武装，否则会沿用旧的 armed_at 直接判过期
            if active and cron.get("repeat_rule") == "none":
                rearmed = True

        # 时间/规则/启用状态变化后，下一次触发从"现在"重新计算
        if rearmed:
            cron["armed_at"] = now_iso
            cron["last_fired_at"] = None

        if description is not None:
            cron["description"] = description

        _write_json(CRON_FILE, crons)
    return {"message": f"闹钟 '{cron['title']}' ({cron['id']}) 修改成功", "cron": cron}


def list_crons() -> List[Dict[str, Any]]:
    """
    获取所有设定的闹钟

    Returns:
        闹钟列表
    """
    return _read_json(CRON_FILE)
