# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lark-oapi",
# ]
# ///

import sys
import json
import threading
import os
import asyncio
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr


def send_json_to_main(method: str, params: dict):
    _REAL_STDOUT.write(
        json.dumps({"method": method, "params": params}, ensure_ascii=False) + "\n"
    )
    _REAL_STDOUT.flush()


APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
DEFAULT_CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "")

client = (
    lark.Client.builder()
    .app_id(APP_ID)
    .app_secret(APP_SECRET)
    .log_level(lark.LogLevel.WARNING)
    .build()
)


def _on_message_received(data: P2ImMessageReceiveV1) -> None:
    msg_type = data.event.message.message_type
    if msg_type != "text":
        print(f"⚠️ [Feishu] 收到非文本消息 ({msg_type})，暂未支持解析")
        return

    msg_content = json.loads(data.event.message.content)
    user_text = msg_content.get("text", "")

    print(f"💬 [Feishu Sensor] 收到用户消息: {user_text}")

    payload = f"[Feishu Sensor 收到用户消息] {user_text}"
    send_json_to_main("observe", {"content": payload})


def start_ws_listener():
    import time

    if not APP_ID or not APP_SECRET:
        print("⚠️ [Feishu] 缺少飞书凭证，无法启动 WebSocket")
        return

    while True:  # 无限重连循环
        try:
            event_handler = (
                lark.EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(_on_message_received)
                .build()
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            import lark_oapi.ws.client as ws_client_module

            ws_client_module.loop = loop
            ws_client = lark.ws.Client(
                APP_ID,
                APP_SECRET,
                event_handler=event_handler,
                log_level=lark.LogLevel.WARNING,
            )
            print("🟢 [Feishu] WebSocket 监听已启动")
            ws_client.start()  # 如果网络断开，这里会结束或抛异常
        except Exception as e:
            print(f"❌ [Feishu] WebSocket 监听崩溃，5秒后重试: {e}")

        time.sleep(5)  # 缓冲时间，防止死循环狂刷日志


def _send_message_task(request):
    try:
        resp = client.im.v1.message.create(request)
        if not resp.success():
            print(f"❌ [Feishu] 发送失败: {resp.msg}")
    except Exception as e:
        print(f"❌ [Feishu] 请求飞书接口异常: {e}")


threading.Thread(target=start_ws_listener, daemon=True).start()

for line in sys.stdin:
    if not line.strip():
        continue
    try:
        req = json.loads(line)
        if req.get("method") == "express":
            message = req["params"].get("message", "")
            kwargs = req["params"].get("kwargs", {})
            receive_id = kwargs.get("target_id", DEFAULT_CHAT_ID)

            id_type = "chat_id"
            if receive_id.startswith("ou_"):
                id_type = "open_id"
            elif receive_id.startswith("on_"):
                id_type = "union_id"
            elif receive_id.startswith("eu_"):
                id_type = "email"

            card_content = {
                "config": {"wide_screen_mode": True},
                "elements": [{"tag": "markdown", "content": message}],
            }
            req_msg = (
                CreateMessageRequest.builder()
                .receive_id_type(id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("interactive")
                    .content(json.dumps(card_content, ensure_ascii=False))
                    .build()
                )
                .build()
            )

            threading.Thread(
                target=_send_message_task, args=(req_msg,), daemon=True
            ).start()
    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"❌ [Feishu] 处理 express 消息时发生未知异常: {e}")
