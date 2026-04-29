"""Cron 闹钟核心操作模块"""

import json
import os
import uuid
from typing import List, Dict, Any

from src.utils.config import CRON_FILE
from src.tool.cron.exceptions import (
    CronNotFoundError,
    InvalidTimeFormatError,
    InvalidRepeatRuleError
)


# 支持的重复规则
VALID_REPEAT_RULES = ["none", "everyday", "weekly_1", "weekly_2", "weekly_3",
                      "weekly_4", "weekly_5", "weekly_6", "weekly_7"]


def _ensure_file(filepath: str):
    """确保文件存在，不存在则创建空列表"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump([], f)


def _read_json(filepath: str) -> List[Dict[str, Any]]:
    """读取 JSON 文件内容"""
    _ensure_file(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_json(filepath: str, data: List[Dict[str, Any]]):
    """写入 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _validate_time_format(time_str: str) -> bool:
    """验证时间格式是否为 HH:MM"""
    import re
    return bool(re.match(r'^([01]\d|2[0-3]):[0-5]\d$', time_str))


def _validate_repeat_rule(rule: str) -> bool:
    """验证重复规则是否有效"""
    return rule in VALID_REPEAT_RULES


def add_cron(title: str, trigger_time: str, repeat_rule: str = "none") -> dict:
    """
    添加闹钟

    Args:
        title: 闹钟标题
        trigger_time: 触发时间，HH:MM 格式（如 08:30）
        repeat_rule: 重复规则，默认 "none"
            - "none": 不重复（一次性）
            - "everyday": 每天
            - "weekly_1" ~ "weekly_7": 每周一到周日

    Returns:
        包含 id, title, trigger_time, repeat_rule, active 的字典
    """
    # 验证时间格式
    if not _validate_time_format(trigger_time):
        raise InvalidTimeFormatError(trigger_time)
    
    # 验证重复规则
    if not _validate_repeat_rule(repeat_rule):
        raise InvalidRepeatRuleError(repeat_rule)
    
    crons = _read_json(CRON_FILE)
    cron_id = "crn_" + str(uuid.uuid4())[:8]
    
    item = {
        "id": cron_id,
        "title": title,
        "trigger_time": trigger_time,
        "repeat_rule": repeat_rule,
        "active": True
    }
    
    crons.append(item)
    _write_json(CRON_FILE, crons)
    
    return item


def delete_cron(cron_id: str) -> dict:
    """
    删除闹钟

    Args:
        cron_id: 闹钟 ID

    Returns:
        包含 message 的字典
    """
    crons = _read_json(CRON_FILE)
    filtered = [c for c in crons if c["id"] != cron_id]
    
    if len(filtered) == len(crons):
        raise CronNotFoundError(cron_id)
    
    _write_json(CRON_FILE, filtered)
    
    return {"message": f"闹钟 {cron_id} 删除成功"}


def update_cron(cron_id: str, title: str = None, trigger_time: str = None, 
                repeat_rule: str = None, active: bool = None) -> dict:
    """
    修改闹钟（可以用于开启/关闭特定闹钟）

    Args:
        cron_id: 闹钟 ID
        title: 新标题（可选）
        trigger_time: 新触发时间（可选）
        repeat_rule: 新重复规则（可选）
        active: 是否激活（可选）

    Returns:
        包含 message 和更新后闹钟信息的字典
    """
    crons = _read_json(CRON_FILE)
    
    for cron in crons:
        if cron["id"] == cron_id:
            # 验证并更新时间格式
            if trigger_time is not None:
                if not _validate_time_format(trigger_time):
                    raise InvalidTimeFormatError(trigger_time)
                cron["trigger_time"] = trigger_time
            
            # 验证并更新重复规则
            if repeat_rule is not None:
                if not _validate_repeat_rule(repeat_rule):
                    raise InvalidRepeatRuleError(repeat_rule)
                cron["repeat_rule"] = repeat_rule
            
            # 更新其他字段
            if title is not None:
                cron["title"] = title
            if active is not None:
                cron["active"] = active
            
            _write_json(CRON_FILE, crons)
            return {"message": f"闹钟 {cron_id} 修改成功", "cron": cron}
    
    raise CronNotFoundError(cron_id)


def list_crons() -> List[Dict[str, Any]]:
    """
    获取所有设定的闹钟

    Returns:
        闹钟列表
    """
    return _read_json(CRON_FILE)