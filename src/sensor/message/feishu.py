import asyncio
import json
import threading
from typing import Any, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

from src.sensor.base import BaseSensor
from src.sensor.gateway import get_gateway


class FeishuSensor(BaseSensor):
    config_key = "feishu"

    def __init__(self, config_dict: dict):
        super().__init__(sensor_type="message", sensor_name="feishu", config_dict=config_dict)
        self.app_id = self.config_dict.get("app_id", "")
        self.app_secret = self.config_dict.get("app_secret", "")
        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

    def _do_p2_im_message_receive_v1(self, data: P2ImMessageReceiveV1) -> None:
        msg_content = json.loads(data.event.message.content)
        user_text = msg_content.get("text", "")
        print(f"\n💬 [Feishu Sensor] 收到用户消息: {user_text}")
        get_gateway().push(self, user_text)

    def _observe(self, *args, **kwargs) -> Optional[Any]:
        if not self.app_id or not self.app_secret:
            print("⚠️ [Feishu Sensor] 缺少飞书凭证，无法启动 WebSocket")
            return None

        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._do_p2_im_message_receive_v1) \
            .build()

        def _run_ws():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            import lark_oapi.ws.client as ws_client_module
            ws_client_module.loop = loop

            ws_client = lark.ws.Client(
                self.app_id, self.app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO
            )

            ws_client.start()

        threading.Thread(target=_run_ws, daemon=True).start()
        print("🟢 [Feishu Sensor] WebSocket 监听已启动")

    def _express(self, message: Any, target_id: Optional[str] = None, **kwargs) -> bool:
        receive_id = target_id if target_id else self.config_dict.get("chat_id", "")
        try:
            req = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(CreateMessageRequestBody.builder()
                              .receive_id(receive_id)
                              .msg_type("text")
                              .content(json.dumps({"text": message}))
                              .build()) \
                .build()
            resp = self.client.im.v1.message.create(req)
            if resp.success():
                print(f"✅ [Feishu Sensor] 成功发送: {message[:50]}...")
                return True
            else:
                print(f"❌ [Feishu Sensor] 发送失败: {resp.msg}")
                return False
        except Exception as e:
            print(f"❌ [Feishu Sensor] 异常报错: {str(e)}")
            return False