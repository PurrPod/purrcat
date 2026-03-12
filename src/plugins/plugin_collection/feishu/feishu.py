import json
import os
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
import threading
with open("data/config/feishu_config.json", "r") as f:
    config = json.load(f)
APP_ID = config["APP_ID"]
APP_SECRET = config["APP_SECRET"]

# 全局初始化飞书发送客户端
client = lark.Client.builder() \
    .app_id(APP_ID) \
    .app_secret(APP_SECRET) \
    .log_level(lark.LogLevel.INFO) \
    .build()



# 全局缓冲队列与线程锁
MESSAGE_BUFFER = []
BUFFER_LOCK = threading.Lock()
# 标记：是否已经向 Agent 的主队列发送过取件通知
NOTIFICATION_SENT = False


def push_feishu_message(chat_id: str, text: str) -> bool:
    """
    传感器专用：把飞书消息推入缓冲。
    返回 True 表示需要唤醒 Agent；返回 False 表示 Agent 已经被通知过了，不用打扰。
    """
    global NOTIFICATION_SENT
    with BUFFER_LOCK:
        MESSAGE_BUFFER.append({"chat_id": chat_id, "text": text})
        if not NOTIFICATION_SENT:
            NOTIFICATION_SENT = True
            return True
        return False


def get_message():
    """
    给 Agent 用的工具：获取缓冲区中所有的飞书未读消息。
    """
    global NOTIFICATION_SENT
    with BUFFER_LOCK:
        if not MESSAGE_BUFFER:
            NOTIFICATION_SENT = False
            return "当前没有任何未读的飞书消息。"
        batch = MESSAGE_BUFFER[:]
        MESSAGE_BUFFER.clear()
        NOTIFICATION_SENT = False
    res = "【飞书未读消息列表】\n"
    for i, msg in enumerate(batch):
        res += f"第 {i + 1} 条 - [会话: {msg['chat_id']}] 内容: {msg['text']}\n"
    return res

def send_message(receive_id: str, text: str, mode: str, receive_id_type: str = "chat_id") -> str:
    """
    给飞书发送文本消息。
    :param receive_id: 接收者的ID。如果回复对话，填写传入的 chat_id；如果主动私聊某人，可以是 open_id 或 user_id。
    :param text: 要发送的纯文本内容。
    :param receive_id_type: ID的类型，默认为 "chat_id" (群聊或单聊的会话ID)。
    """
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
            if mode == "continue":
                return f"🌟 飞书发送成功！请继续你的工作"
            return "__AGENT_PAUSE__"
        else:
            return f"❌ 飞书发送失败 | Code: {resp.code} | Msg: {resp.msg} | LogId: {resp.get_log_id()}"

    except Exception as e:
        return f"❌ 飞书发送工具发生异常: {str(e)}"