"""Memo 备忘录核心操作模块"""

import json
import os
import uuid
from typing import List, Dict, Any, Tuple

from src.utils.config import MEMORY_PENDING_DIR


def _validate_params(short_term: str = None, events: list = None,
                     work_exp: list = None, cognition: list = None,
                     reminders: str = None, project_state: str = None) -> tuple:
    """
    参数校验

    Returns:
        (valid_events, valid_work_exp, valid_cognition, errors)
    """
    errors = []

    if not short_term or not short_term.strip():
        errors.append("short_term 不能为空，请提供当前工作上下文")

    valid_events = []
    if events is not None:
        if not isinstance(events, list):
            errors.append(f"events 必须是数组，收到 {type(events).__name__}")
        else:
            for i, e in enumerate(events):
                if not isinstance(e, dict):
                    errors.append(f"events[{i}] 无效：每条事件必须是对象 {{time, event}}")
                elif "time" not in e or "event" not in e:
                    errors.append(f"events[{i}] 缺少字段：需要 time 和 event")
                elif not isinstance(e["time"], str) or not e["time"].strip():
                    errors.append(f"events[{i}].time 无效：必须是非空字符串")
                elif not isinstance(e["event"], str) or not e["event"].strip():
                    errors.append(f"events[{i}].event 无效：必须是非空字符串")
                else:
                    valid_events.append({"time": e["time"].strip(), "event": e["event"].strip()})

    valid_work_exp = []
    if work_exp is not None:
        if not isinstance(work_exp, list):
            errors.append(f"work_exp 必须是数组，收到 {type(work_exp).__name__}")
        else:
            for i, w in enumerate(work_exp):
                if not isinstance(w, str) or not w.strip():
                    errors.append(f"work_exp[{i}] 无效：每条经验必须是非空字符串")
                elif len(w.strip()) > 500:
                    errors.append(f"work_exp[{i}] 过长（{len(w.strip())}字符），建议每条不超过500字符")
                else:
                    valid_work_exp.append(w.strip())

    valid_cog = []
    if cognition is not None:
        if not isinstance(cognition, list):
            errors.append(f"cognition 必须是数组，收到 {type(cognition).__name__}")
        else:
            for i, c in enumerate(cognition):
                if not isinstance(c, str) or not c.strip():
                    errors.append(f"cognition[{i}] 无效：每条认知必须是非空字符串")
                elif len(c.strip()) > 500:
                    errors.append(f"cognition[{i}] 过长（{len(c.strip())}字符），建议每条不超过500字符")
                else:
                    valid_cog.append(c.strip())

    if reminders is not None and not isinstance(reminders, str):
        errors.append("reminders 必须是字符串")

    if project_state is not None and not isinstance(project_state, str):
        errors.append("project_state 必须是字符串")

    return valid_events, valid_work_exp, valid_cog, errors


def _write_to_pending(
    short_term: str,
    events: list,
    work_exp: list,
    cognition: list,
    reminders: str,
    project_state: str
) -> str:
    """
    将记忆数据写入 pending 目录的 JSON 文件

    注意：short_term、reminders、project_state 暂不写入 JSON，
    由 Memory Worker 根据需要从其他渠道获取或忽略。

    Returns:
        写入的文件路径
    """
    import datetime

    os.makedirs(MEMORY_PENDING_DIR, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"memory_{timestamp}_{unique_id}.json"
    filepath = os.path.join(MEMORY_PENDING_DIR, filename)

    data = {
        "events": events or [],
        "work_exp": work_exp or [],
        "cognition": cognition or [],
        "timestamp": timestamp,
        "source": "main agent",
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath
