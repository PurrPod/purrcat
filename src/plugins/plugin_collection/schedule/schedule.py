import json
import os
import uuid
from typing import Any
from src.utils.config import SCHEDULE_FILE, CRON_FILE
USER_REPLY_FUTURES = {}
def _ensure_file(filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump([], f)

def _read_json(filepath):
    _ensure_file(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def _write_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)
def add_schedule(title: str, start_time: str, end_time: str, description: str = "") -> str:
    """添加跨天/跨月的日程。时间格式推荐 YYYY-MM-DD HH:MM"""
    schedules = _read_json(SCHEDULE_FILE)
    item = {
        "id": "sch_" + str(uuid.uuid4())[:8],
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description
    }
    schedules.append(item)
    _write_json(SCHEDULE_FILE, schedules)
    return _format_response("text",f"✅ 日程添加成功: {title} ({start_time} 至 {end_time})")

def delete_schedule(schedule_id: str) -> str:
    """删除日程"""
    schedules = _read_json(SCHEDULE_FILE)
    filtered = [s for s in schedules if s["id"] != schedule_id]
    if len(filtered) == len(schedules): return _format_response("error",f"❌ 找不到日程ID: {schedule_id}")
    _write_json(SCHEDULE_FILE, filtered)
    return _format_response("text",f"✅ 日程 {schedule_id} 删除成功")

def update_schedule(schedule_id: str, title: str = None, start_time: str = None, end_time: str = None, description: str = None) -> str:
    """修改日程"""
    schedules = _read_json(SCHEDULE_FILE)
    for s in schedules:
        if s["id"] == schedule_id:
            if title is not None: s["title"] = title
            if start_time is not None: s["start_time"] = start_time
            if end_time is not None: s["end_time"] = end_time
            if description is not None: s["description"] = description
            _write_json(SCHEDULE_FILE, schedules)
            return _format_response("text",f"✅ 日程 {schedule_id} 修改成功")
    return _format_response("error",f"❌ 找不到日程ID: {schedule_id}")

def get_schedules(date_str: str = None) -> str:
    """获取所有日程，或者根据特定日期 (YYYY-MM-DD) 检索"""
    schedules = _read_json(SCHEDULE_FILE)
    if date_str:
        schedules = [s for s in schedules if date_str in s["start_time"] or date_str in s["end_time"]]
    return _format_response("text","\n".join(str(schedules)))

def add_cron(title: str, trigger_time: str, repeat_rule: str = "none") -> str:
    """
    添加闹钟。
    trigger_time: HH:MM 格式 (如 08:30)
    repeat_rule: "none"(不重复), "everyday"(每天), "weekly_1"(每周一)..."weekly_7"(每周日)
    """
    crons = _read_json(CRON_FILE)
    item = {
        "id": "crn_" + str(uuid.uuid4())[:8],
        "title": title,
        "trigger_time": trigger_time,
        "repeat_rule": repeat_rule,
        "active": True
    }
    crons.append(item)
    _write_json(CRON_FILE, crons)
    return _format_response("text",f"✅ 闹钟设定成功: {title} ({trigger_time}, 规则: {repeat_rule})")

def delete_cron(cron_id: str) -> str:
    """删除闹钟"""
    crons = _read_json(CRON_FILE)
    filtered = [c for c in crons if c["id"] != cron_id]
    if len(filtered) == len(crons): return _format_response("error",f"❌ 找不到闹钟ID: {cron_id}")
    _write_json(CRON_FILE, filtered)
    return _format_response("text",f"✅ 闹钟 {cron_id} 删除成功")

def update_cron(cron_id: str, title: str = None, trigger_time: str = None, repeat_rule: str = None, active: bool = None) -> str:
    """修改闹钟（可以用于开启/关闭特定闹钟）"""
    crons = _read_json(CRON_FILE)
    for c in crons:
        if c["id"] == cron_id:
            if title is not None: c["title"] = title
            if trigger_time is not None: c["trigger_time"] = trigger_time
            if repeat_rule is not None: c["repeat_rule"] = repeat_rule
            if active is not None: c["active"] = active
            _write_json(CRON_FILE, crons)
            return _format_response("text",f"✅ 闹钟 {cron_id} 修改成功")
    return _format_response("error",f"❌ 找不到闹钟ID: {cron_id}")

def get_crons() -> str:
    """获取设定的所有闹钟"""
    crons = _read_json(CRON_FILE)
    return _format_response("text", str(crons))




