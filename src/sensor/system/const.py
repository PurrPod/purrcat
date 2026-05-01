import time
import json
import os
import threading
import datetime
from typing import Any, Optional

from src.sensor.base import BaseSensor
from src.sensor.gateway import get_gateway
from src.utils.config import CRON_FILE, SCHEDULE_FILE


HARNESS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "agent", "core", "HARNESS.md")


class SystemSensor(BaseSensor):
    def __init__(self):
        super().__init__(sensor_type="system", sensor_name="system_clock")

    def _observe(self, *args, **kwargs) -> None:
        from src.utils.config import get_sensor_config
        cfg = get_sensor_config().get("heartbeat", {})

        t1 = threading.Thread(target=self._heartbeat_loop, args=(cfg,), daemon=True)
        t1.start()

        t2 = threading.Thread(target=self._clock_loop, daemon=True)
        t2.start()
        print("🟢 [System Sensor] 心跳与时钟监听已启动")

    def _heartbeat_loop(self, cfg):
        interval = cfg.get("interval", 1800)
        heartbeat_content = "【系统心跳】如果你现在无事可干，可尝试 Fetch 一下 harness 或 todo 看看闲时要求"
        total_time = 0
        while True:
            time.sleep(10)
            total_time += 10
            if total_time >= interval:
                total_time = 0
                get_gateway().push(self, heartbeat_content)

    def _clock_loop(self):
        cron_file = CRON_FILE
        schedule_file = SCHEDULE_FILE
        while True:
            now = datetime.datetime.now()
            current_time = now.strftime("%H:%M")
            current_weekday = str(now.isoweekday())

            if os.path.exists(cron_file):
                try:
                    with open(cron_file, "r", encoding="utf-8") as f:
                        crons = json.load(f)
                    updated = False
                    for c in crons:
                        if not c.get("active"):
                            continue
                        rule = c.get("repeat_rule", "none")
                        is_match = False
                        if c.get("trigger_time") == current_time:
                            if rule == "everyday" or rule == "none":
                                is_match = True
                            elif rule.startswith("weekly_") and rule.split("_")[1] == current_weekday:
                                is_match = True
                        if is_match:
                            get_gateway().push(self, f"⏰【闹钟铃声】时间到！事项: {c.get('title')}")
                            if rule == "none":
                                c["active"] = False
                                updated = True
                    if updated:
                        with open(cron_file, "w", encoding="utf-8") as f:
                            json.dump(crons, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            if os.path.exists(schedule_file):
                try:
                    with open(schedule_file, "r", encoding="utf-8") as f:
                        schedules = json.load(f)
                    for s in schedules:
                        start_time_str = s.get("start_time")
                        if start_time_str:
                            try:
                                if 'T' in start_time_str:
                                    fmt = "%Y-%m-%dT%H:%M:%S" if len(start_time_str) > 16 else "%Y-%m-%dT%H:%M"
                                else:
                                    fmt = "%Y-%m-%d %H:%M:%S" if len(start_time_str) > 16 else "%Y-%m-%d %H:%M"
                                st_dt = datetime.datetime.strptime(start_time_str, fmt)
                                delta = (st_dt - now).total_seconds()
                                if 14 * 60 <= delta < 15 * 60:
                                    get_gateway().push(self, f"📅【日程预警】15分钟后即将开始: {s.get('title')}。请做好准备。")
                            except:
                                pass
                except Exception:
                    pass

            time.sleep(60)

    def _express(self, message: Any, **kwargs) -> bool:
        return False


_system_sensor = SystemSensor()


def get_system_sensor() -> SystemSensor:
    return _system_sensor


def start_sensors():
    from src.utils.config import get_sensor_config
    heartbeat_cfg = get_sensor_config().get("heartbeat", {})
    if heartbeat_cfg.get("enabled", False):
        interval_min = heartbeat_cfg.get("interval", 1800) // 60
        print(f"💓 系统心跳传感器已上线（每{interval_min}分钟）")
    _system_sensor.observe()