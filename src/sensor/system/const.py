import time
import json
import os
import threading
import datetime
from typing import Any, Optional

from src.sensor.base import BaseSensor
from src.sensor.gateway import get_gateway
from src.utils.config import CRON_FILE, SCHEDULE_FILE


class SystemSensor(BaseSensor):
    config_key = "heartbeat"

    def __init__(self, config_dict: dict):
        super().__init__(sensor_type="system", sensor_name="system_clock", config_dict=config_dict)
        self.interval = self.config_dict.get("interval", 1800)

    def _observe(self, *args, **kwargs) -> None:
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        threading.Thread(target=self._clock_loop, daemon=True).start()
        print("🟢 [System Sensor] 心跳与时钟守护已启动")

    def _heartbeat_loop(self):
        total_time = 0
        heartbeat_content = "⏰ [Heartbeat] Fetch harness todo"
        while True:
            time.sleep(10)
            total_time += 10
            if total_time >= self.interval:
                total_time = 0
                get_gateway().push(self, heartbeat_content)

    def _clock_loop(self):
        while True:
            now = datetime.datetime.now()
            current_time = now.strftime("%H:%M")
            current_weekday = str(now.isoweekday())

            if os.path.exists(CRON_FILE):
                try:
                    with open(CRON_FILE, "r", encoding="utf-8") as f:
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
                        with open(CRON_FILE, "w", encoding="utf-8") as f:
                            json.dump(crons, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            if os.path.exists(SCHEDULE_FILE):
                try:
                    with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
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
                            except Exception:
                                pass
                except Exception:
                    pass

            time.sleep(60)

    def _express(self, message: Any, **kwargs) -> bool:
        return False