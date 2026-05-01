import feedparser
import json
import os
import time
import threading
import requests
from typing import Any, Optional

from src.sensor.base import BaseSensor
from src.sensor.gateway import get_gateway


class RSSSensor(BaseSensor):
    def __init__(self, name: str, rss_url: str, seen_ids: set, config_dict: dict):
        super().__init__(sensor_type="rss_update", sensor_name=name, config_dict=config_dict)
        self.rss_url = rss_url
        self.seen_ids = seen_ids

    def _observe(self, *args, **kwargs) -> None:
        new_entries, _ = self.fetch_new_entries()
        if new_entries:
            output_lines = [f"### {self.sensor_name} 有新更新"]
            for entry in new_entries[:3]:
                title = getattr(entry, 'title', '').strip()
                link = getattr(entry, 'link', '').strip()
                output_lines.append(f"- [{title}]({link})")
            if len(new_entries) > 3:
                output_lines.append(f"- *(还有 {len(new_entries) - 3} 条更新未展示)*")
            result_text = "\n".join(output_lines)
            get_gateway().push(self, result_text)

    def _express(self, message: Any, **kwargs) -> bool:
        return False

    def fetch_new_entries(self) -> tuple[list, list]:
        new_entries = []
        logs = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive"
            }
            response = requests.get(self.rss_url, headers=headers, timeout=15)
            response.raise_for_status()
            feed_data = feedparser.parse(response.content)
            if getattr(feed_data, 'bozo', 0) == 1:
                logs.append(f"[{self.sensor_name}] 格式有瑕疵")
            for entry in getattr(feed_data, 'entries', []):
                entry_id = getattr(entry, 'id', getattr(entry, 'link', getattr(entry, 'title', '')))
                if not entry_id:
                    continue
                if entry_id not in self.seen_ids:
                    new_entries.append(entry)
                    self.seen_ids.add(entry_id)
            return new_entries, logs
        except requests.exceptions.RequestException as re:
            logs.append(f"[{self.sensor_name}] 网络请求失败: {re}")
            return [], logs
        except Exception as e:
            logs.append(f"[{self.sensor_name}] 解析失败: {e}")
            return [], []


class RSSListener(BaseSensor):
    config_key = "rss"

    def __init__(self, config_dict: dict):
        super().__init__(sensor_type="subscribe", sensor_name="rss_listener", config_dict=config_dict)
        self.cache_file = "rss_history.json"
        self.history_dict = self._load_history()
        self.sensors = []
        subscriptions = self.config_dict.get("subscriptions", [])
        for item in subscriptions:
            name = item["name"]
            seen_ids = set(self.history_dict.get(name, []))
            sensor = RSSSensor(name=name, rss_url=item["rss_url"], seen_ids=seen_ids, config_dict=config_dict)
            self.sensors.append(sensor)
            get_gateway().register(sensor)

    def _load_history(self) -> dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_history(self):
        for sensor in self.sensors:
            self.history_dict[sensor.sensor_name] = list(sensor.seen_ids)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.history_dict, f, ensure_ascii=False, indent=2)

    def _poll_loop(self, interval: int):
        while True:
            time.sleep(interval)
            for sensor in self.sensors:
                sensor.observe()
            self._save_history()

    def _observe(self, *args, **kwargs) -> None:
        interval = self.config_dict.get("interval", 1800)
        t = threading.Thread(target=self._poll_loop, args=(interval,), daemon=True)
        t.start()
        print(f"🟢 [RSS Listener] 轮询已启动（间隔 {interval} 秒）")

    def _express(self, message: Any, **kwargs) -> bool:
        return False