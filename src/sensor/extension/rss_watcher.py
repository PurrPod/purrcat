# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "feedparser",
#     "requests"
# ]
# ///

import sys
import json
import time
import os
import feedparser
import requests

_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr


def send_json_to_main(method: str, params: dict):
    _REAL_STDOUT.write(
        json.dumps({"method": method, "params": params}, ensure_ascii=False) + "\n"
    )
    _REAL_STDOUT.flush()


INTERVAL = int(os.environ.get("INTERVAL", "1800"))
CACHE_FILE = os.path.join(os.path.dirname(__file__), "rss_history.json")
SUBS_JSON = os.environ.get("RSS_SUBSCRIPTIONS_JSON", "[]")

try:
    subscriptions = json.loads(SUBS_JSON)
except json.JSONDecodeError:
    subscriptions = []
    print("⚠️ [RSS] RSS_SUBSCRIPTIONS_JSON 格式错误")

history = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        pass

print(f"🟢 [RSS] 轮询已启动（间隔 {INTERVAL} 秒）")

while True:
    updated = False
    for sub in subscriptions:
        name = sub.get("name")
        url = sub.get("rss_url")
        seen = set(history.get(name, []))

        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            feed_data = feedparser.parse(resp.content)

            new_entries = []
            for entry in getattr(feed_data, "entries", []):
                entry_id = getattr(
                    entry, "id", getattr(entry, "link", getattr(entry, "title", ""))
                )
                if entry_id and entry_id not in seen:
                    new_entries.append(entry)
                    seen.add(entry_id)

            if new_entries:
                output_lines = [f"### {name} 有新更新"]
                for entry in new_entries[:3]:
                    output_lines.append(
                        f"- [{getattr(entry, 'title', '').strip()}]({getattr(entry, 'link', '').strip()})"
                    )
                if len(new_entries) > 3:
                    output_lines.append(
                        f"- *(还有 {len(new_entries) - 3} 条更新未展示)*"
                    )

                send_json_to_main("observe", {"content": "\n".join(output_lines)})
                history[name] = list(seen)
                updated = True
        except Exception as e:
            print(f"❌ [RSS] 抓取 {name} 失败: {e}")

    if updated:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)

    time.sleep(INTERVAL)
