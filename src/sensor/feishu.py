import json
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from src.agent.agent import add_message
from src.plugins.plugin_collection.feishu.feishu import push_feishu_message

with open("data/config/feishu_config.json", "r") as f:
    config = json.load(f)
APP_ID = config["APP_ID"]
APP_SECRET = config["APP_SECRET"]

def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    msg_content = json.loads(data.event.message.content)
    user_text = msg_content.get("text", "")
    chat_id = data.event.message.chat_id
    print(f"\n📩 [Lark Sensor] 收到飞书消息: {user_text} (已放入缓冲池)")
    needs_notify = push_feishu_message(chat_id, user_text)
    if needs_notify:
        add_message({
            "type": "owner_message",
            "content": "飞书收到了新的用户消息，调用消息获取工具查看缓冲区的具体内容！"
        })

event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
    .build()


def _run_ws_client():
    ws_client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO
    )
    ws_client.start()


def start_lark_sensor():
    t = threading.Thread(target=_run_ws_client, daemon=True)
    t.start()
    print("📡 飞书 WebSocket 长连接传感器已启动！")