"""
记忆系统的公共工具模块，处理数据的统一校验、格式化与缓冲下发
"""
import json
import os
import re
import uuid
from datetime import datetime

from src.utils.config import MEMORY_PENDING_DIR


def normalize_iso_time(time_str: str) -> str:
    """将各种非标时间字符串统一清洗为 ISO 8601 格式"""
    time_str = time_str.strip()
    # 纯日期格式：20260515 -> 2026-05-15T00:00:00
    if re.match(r"^\d{8}$", time_str):
        return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}T00:00:00"
    # 紧凑格式带时间：20260515 11:32 -> 2026-05-15T11:32:00
    elif re.match(r"^\d{8} \d{2}:\d{2}$", time_str):
        return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}T{time_str[9:14]}:00"
    # 标准日期格式：2026-05-15 -> 2026-05-15T00:00:00
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", time_str):
        return f"{time_str}T00:00:00"
    # 精确到分钟：2026-05-15 11:32 或 2026-05-15T11:32 -> 2026-05-15T11:32:00
    elif re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}$", time_str):
        return time_str.replace(" ", "T") + ":00"
    # 已包含秒数的格式，统一空格为T
    elif re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$", time_str):
        return time_str.replace(" ", "T")
    return time_str


def validate_memo_data(memo_data: dict) -> tuple[dict, list]:
    """校验 memo_data 参数，返回 (valid_data, errors)"""
    errors = []
    valid_data = {
        "short_term": "",
        "work_exp": [],
        "user_profile": [],
        "events": [],
        "cognition": [],
    }

    if not isinstance(memo_data, dict):
        return {}, ["memo_data 必须是对象"]

    short_term = memo_data.get("short_term")
    if short_term is not None and not isinstance(short_term, str):
        errors.append(f"short_term 必须是字符串，收到 {type(short_term).__name__}")
    elif short_term:
        valid_data["short_term"] = short_term.strip()

    work_exp = memo_data.get("work_exp", [])
    if not isinstance(work_exp, list):
        errors.append(f"work_exp 必须是数组，收到 {type(work_exp).__name__}")
    else:
        for i, w in enumerate(work_exp):
            if not isinstance(w, str) or not w.strip():
                errors.append(f"work_exp[{i}] 无效：每条经验必须是非空字符串")
            else:
                valid_data["work_exp"].append(w.strip())

    user_profile = memo_data.get("user_profile", [])
    if not isinstance(user_profile, list):
        errors.append(f"user_profile 必须是数组，收到 {type(user_profile).__name__}")
    else:
        for i, u in enumerate(user_profile):
            if not isinstance(u, str) or not u.strip():
                errors.append(f"user_profile[{i}] 无效：每条画像必须是非空字符串")
            else:
                valid_data["user_profile"].append(u.strip())

    events = memo_data.get("events", [])
    if not isinstance(events, list):
        errors.append(f"events 必须是数组，收到 {type(events).__name__}")
    else:
        for i, e in enumerate(events):
            if not isinstance(e, dict) or "time" not in e or "event" not in e:
                errors.append(f"events[{i}] 无效：必须是包含 time 和 event 的对象")
                continue
            time_str = str(e["time"]).strip()
            time_pattern = (
                r"^(\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?|\d{8}( \d{2}:\d{2})?)$"
            )
            if not re.match(time_pattern, time_str):
                errors.append(f"events[{i}].time 格式无效，期望 YYYY-MM-DD HH:MM")
            else:
                valid_data["events"].append(
                    {
                        "time": normalize_iso_time(time_str),
                        "event": str(e["event"]).strip(),
                    }
                )

    cognition = memo_data.get("cognition", [])
    if not isinstance(cognition, list):
        errors.append(f"cognition 必须是数组，收到 {type(cognition).__name__}")
    else:
        for i, c in enumerate(cognition):
            if not isinstance(c, str) or not c.strip():
                errors.append(f"cognition[{i}] 无效：必须是非空字符串")
            else:
                valid_data["cognition"].append(c.strip())

    return valid_data, errors


def write_to_pending(
    events: list,
    cognition: list,
    user_profile: list,
    work_exp: list,
    source: str = "system",
) -> str:
    """将待处理记忆写入 pending 目录，供后台 worker 抓取"""
    os.makedirs(MEMORY_PENDING_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"memory_{timestamp}_{unique_id}.json"
    filepath = os.path.join(MEMORY_PENDING_DIR, filename)

    data = {
        "user_profile": user_profile or [],
        "work_exp": work_exp or [],
        "events": events or [],
        "cognition": cognition or [],
        "timestamp": timestamp,
        "source": source,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath
