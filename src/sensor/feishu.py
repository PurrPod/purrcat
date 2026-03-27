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

    print(f"\n📩 [feishu Sensor] 收到飞书消息: {user_text} (准备强制注入)")

    if GLOBAL_AGENT:
        # 1. 直接强插进 Agent 的对话历史 (支持携带 chat_id 供上下文参考)
        GLOBAL_AGENT.force_push(f"【feishu指令】{user_text}")

        if GLOBAL_AGENT.state == "idle":
            add_message({
                "type": "owner_message",
                "chat_id": chat_id,
                "content": "收到新的feishu消息，请结合最新上下文给出回应或执行任务。如已处理，请忽略"
            })
    else:
        print("⚠️ [Feishu Sensor] 未绑定 Agent 实例，无法执行 force_push！")


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




client = lark.Client.builder() \
    .app_id(APP_ID) \
    .app_secret(APP_SECRET) \
    .log_level(lark.LogLevel.INFO) \
    .build()


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def send_feishu_message(text: str, mode: str = "continue") -> str:
    with open("data/config/feishu_config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    receive_id = config["CHAT_ID"]
    receive_id_type = "chat_id"
    try:
        req = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(CreateMessageRequestBody.builder()
                          .receive_id(receive_id)
                          .msg_type("text")
                          .content(json.dumps({"text": text}))
                          .build()) \
            .build()
        resp = client.im.v1.message.create(req)
        if resp.success():
            # 恢复你原本的 mode 判断逻辑
            if mode == "continue":
                return _format_response("text", "🌟 feishu发送成功！")
            return "__AGENT_PAUSE__"
        else:
            return _format_response("error", f"❌ feishu发送失败 | {resp.msg}")
    except Exception as e:
        return _format_response("error", f"❌ feishu工具异常: {str(e)}")