import json
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from src.agent.agent import add_message, MESSAGE_QUEUE

with open("data/config/feishu_config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
APP_ID = config["APP_ID"]
APP_SECRET = config["APP_SECRET"]

# 用于保存 cat-in-cup 的 Agent 实例
GLOBAL_AGENT = None

def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    msg_content = json.loads(data.event.message.content)
    user_text = msg_content.get("text", "")
    chat_id = data.event.message.chat_id

    print(f"\n📩 [Lark Sensor] 收到飞书消息: {user_text} (准备强制注入)")

    if GLOBAL_AGENT:
        # 1. 直接强插进 Agent 的对话历史 (支持携带 chat_id 供上下文参考)
        GLOBAL_AGENT.force_push(f"【飞书指令】{user_text}")

        if GLOBAL_AGENT.state == "idle":
            add_message({
                "type": "owner_message",
                "chat_id": chat_id,
                "content": "收到新的飞书消息，请结合最新上下文给出回应或执行任务。如已处理，请忽略"
            })
    else:
        print("⚠️ [Lark Sensor] 未绑定 Agent 实例，无法执行 force_push！")


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


def start_lark_sensor(agent_instance=None):
    global GLOBAL_AGENT
    if agent_instance:
        GLOBAL_AGENT = agent_instance
    t = threading.Thread(target=_run_ws_client, daemon=True)
    t.start()
    print("📡 飞书 WebSocket 长连接传感器已启动！")