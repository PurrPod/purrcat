import time
import json
import os
import threading
import datetime
from src.agent.manager import get_agent
from src.utils.config import CRON_FILE, SCHEDULE_FILE


HARNESS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "agent", "core", "HARNESS.md")


def heartbeat():
    from src.utils.config import get_sensor_config
    heartbeat_cfg = get_sensor_config().get("heartbeat", {})
    interval = heartbeat_cfg.get("interval", 1800)
    heartbeat_content = "【系统心跳】如果你现在无事可干，可尝试 Fetch 一下 harness 或 todo 看看闲时要求"
    total_time = 0
    while True:
        agent = get_agent()
        if not agent:
            continue
        if agent.pending_force_push or agent.state == "handling":
            total_time = 0
            continue  # skip if agent is already busy
        time.sleep(10)
        total_time += 10
        if total_time >= interval:
            total_time = 0
            agent.force_push(heartbeat_content, type="heartbeat")


def clock_sensor():
    # 使用固定路径
    cron_file = CRON_FILE
    schedule_file = SCHEDULE_FILE
    while True:
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        current_weekday = str(now.isoweekday())  # 1-7 (周一到周日)
        # 1. 扫描闹钟 (Cron)
        if os.path.exists(cron_file):
            try:
                with open(cron_file, "r", encoding="utf-8") as f:
                    crons = json.load(f)
                updated = False
                for c in crons:
                    if not c.get("active"): continue
                    rule = c.get("repeat_rule", "none")
                    is_match = False
                    if c.get("trigger_time") == current_time:
                        if rule == "everyday" or rule == "none":
                            is_match = True
                        elif rule.startswith("weekly_") and rule.split("_")[1] == current_weekday:
                            is_match = True
                    if is_match:
                        agent = get_agent()
                        if agent:
                            agent.force_push(f"⏰【闹钟铃声】时间到！事项: {c.get('title')}", type="schedule")
                        # 如果是不重复的闹钟，响完即关闭
                        if rule == "none":
                            c["active"] = False
                            updated = True
                if updated:
                    with open(cron_file, "w", encoding="utf-8") as f:
                        json.dump(crons, f, ensure_ascii=False, indent=2)
            except Exception as e:
                pass
        # 2. 扫描日程 (Schedule) - 提前 15 分钟发出日历提醒
        if os.path.exists(schedule_file):
            try:
                with open(schedule_file, "r", encoding="utf-8") as f:
                    schedules = json.load(f)
                for s in schedules:
                    start_time_str = s.get("start_time")  # e.g. "2026-03-07 10:00"
                    if start_time_str:
                        try:
                            # 长度判断兼容带秒和不带秒
                            if 'T' in start_time_str:
                                fmt = "%Y-%m-%dT%H:%M:%S" if len(start_time_str) > 16 else "%Y-%m-%dT%H:%M"
                            else:
                                fmt = "%Y-%m-%d %H:%M:%S" if len(start_time_str) > 16 else "%Y-%m-%d %H:%M"
                            st_dt = datetime.datetime.strptime(start_time_str, fmt)
                            # 计算距离开始的误差
                            delta = (st_dt - now).total_seconds()
                            # 如果刚好落在 14-15 分钟的区间内
                            if 14 * 60 <= delta < 15 * 60:
                                agent = get_agent()
                                if agent:
                                    agent.force_push(f"📅【日程预警】15分钟后即将开始: {s.get('title')}。请做好准备。", type="schedule")
                        except:
                            pass
            except Exception:
                pass
        time.sleep(60)

def start_sensors():
    from src.utils.config import get_sensor_config
    heartbeat_cfg = get_sensor_config().get("heartbeat", {})
    if heartbeat_cfg.get("enabled", False):
        t1 = threading.Thread(target=heartbeat, daemon=True)
        t1.start()
        interval_min = heartbeat_cfg.get("interval", 1800) // 60
        print(f"💓 系统心跳传感器已上线（每{interval_min}分钟）")
    t2 = threading.Thread(target=clock_sensor, daemon=True)
    t2.start()
    print("📡 Clock 传感器已上线。")