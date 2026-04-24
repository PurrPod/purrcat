import feedparser
import json
import os
import requests

from src.agent.manager import get_agent


class RSSSensor:
    def __init__(self, name: str, rss_url: str, seen_ids: set):
        self.name = name
        self.rss_url = rss_url
        self.seen_ids = seen_ids
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
                logs.append(f"[{self.name}] 格式有瑕疵或非标准 XML")

            for entry in getattr(feed_data, 'entries', []):
                entry_id = getattr(entry, 'id', getattr(entry, 'link', getattr(entry, 'title', '')))
                if not entry_id:
                    continue
                if entry_id not in self.seen_ids:
                    new_entries.append(entry)
                    self.seen_ids.add(entry_id)
            return new_entries, logs
        except requests.exceptions.RequestException as re:
            logs.append(f"[{self.name}] 网络请求失败: {re}")
            return [], logs
        except Exception as e:
            logs.append(f"[{self.name}] 解析严重失败: {e}")
            return [], logs

class RSSListener:
    def __init__(self, config_list: list, cache_file: str = "rss_history.json"):
        self.cache_file = cache_file
        self.history_dict = self._load_history()
        self.sensors = []
        for item in config_list:
            name = item["name"]
            seen_ids = set(self.history_dict.get(name, []))
            sensor = RSSSensor(name=name, rss_url=item["rss_url"], seen_ids=seen_ids)
            self.sensors.append(sensor)

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
            self.history_dict[sensor.name] = list(sensor.seen_ids)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.history_dict, f, ensure_ascii=False, indent=2)

    def check_all(self) -> str:
        """执行扫描，并返回适合发送给 Agent 的精简文本"""
        output_lines = []
        total_new_items = 0
        for sensor in self.sensors:
            new_entries, _ = sensor.fetch_new_entries()
            if not new_entries:
                continue
            total_new_items += len(new_entries)
            output_lines.append(f"### {sensor.name}")
            display_entries = new_entries[:3]
            for entry in display_entries:
                title = getattr(entry, 'title', '无标题').strip()
                link = getattr(entry, 'link', '无链接').strip()
                output_lines.append(f"- [{title}]({link})")
            if len(new_entries) > 3:
                output_lines.append(f"- *(还有 {len(new_entries) - 3} 条更新未展示)*")
            output_lines.append("")

        self._save_history()
        if not output_lines:
            return "暂无新的内容更新。"
        output_lines = ["【RSS订阅源每日推送】\n"]+output_lines
        result_text = "\n".join(output_lines).strip()
        agent = get_agent()
        if agent:
            agent.force_push(result_text, source="rss")
        return result_text


if __name__ == "__main__":
    from src.utils.config import get_rss_subscriptions
    rss_config = get_rss_subscriptions()
    if rss_config:
        listener = RSSListener(rss_config)
        result_text = listener.check_all()
        print(result_text)
    else:
        print("未找到 RSS 配置！")