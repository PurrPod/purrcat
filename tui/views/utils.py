import json


def parse_events_content(content: str):
    """解析 events JSON 格式的消息内容"""
    user_messages = []
    system_count = 0

    try:
        data = json.loads(content)
        if "events" in data:
            for event in data["events"]:
                event_type = event.get("type", "")
                event_content = event.get("content", "")
                event_time = event.get("time", "")

                if event_type == "user":
                    user_messages.append((event_time, event_content))
                else:
                    system_count += 1
    except (json.JSONDecodeError, Exception):
        # 如果不是 JSON 格式，当作普通用户消息处理
        user_messages.append(("", content))

    return user_messages, system_count
