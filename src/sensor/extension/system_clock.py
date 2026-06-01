# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import sys
import json
import threading
import time
import datetime
import os

_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

def send_json_to_main(method: str, params: dict):
    _REAL_STDOUT.write(json.dumps({"method": method, "params": params}, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()

INTERVAL = int(os.environ.get("INTERVAL", "1800"))
CRON_FILE = os.environ.get("CRON_FILE", ".purrcat/core/cron.json")

def heartbeat_loop():
    total_time = 0
    while True:
        time.sleep(10)
        total_time += 10
        if total_time >= INTERVAL:
            total_time = 0
            send_json_to_main("observe", {"content": "⏰ [Heartbeat] Fetch solo todo"})

def clock_loop():
    while True:
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        current_weekday = str(now.isoweekday())

        if os.path.exists(CRON_FILE):
            try:
                with open(CRON_FILE, "r", encoding="utf-8") as f: crons = json.load(f)
                updated = False
                for c in crons:
                    if not c.get("active"): continue
                    rule = c.get("repeat_rule", "none")
                    is_match = False
                    if c.get("trigger_time") == current_time:
                        if rule in ["everyday", "none"] or (rule.startswith("weekly_") and rule.split("_")[1] == current_weekday):
                            is_match = True
                    if is_match:
                        desc_text = f"\n详细说明: {c.get('description')}" if c.get('description') else ""
                        send_json_to_main("observe", {"content": f"⏰【闹钟铃声】时间到！事项: {c.get('title')}{desc_text}"})
                        if rule == "none":
                            c["active"] = False
                            updated = True
                if updated:
                    with open(CRON_FILE, "w", encoding="utf-8") as f: json.dump(crons, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ [System Clock] 读取闹钟失败: {e}")

        time.sleep(60)

print("🟢 [System Clock] 心跳与时钟守护已启动")
threading.Thread(target=heartbeat_loop, daemon=True).start()
clock_loop()