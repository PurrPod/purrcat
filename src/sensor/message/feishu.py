import json
import threading
from typing import Any, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

from src.sensor.base import BaseSensor
from src.sensor.gateway import get_gateway
from src.utils.config import get_sensor_config


def _get_feishu_config():
    return get_sensor_config().get("feishu", {})


class FeishuSensor(BaseSensor):
    def __init__(self):
        super().__init__(sensor_type="message", sensor_name="feishu")
        self.feishu_config = _get_feishu_config()
        self.app_id = self.feishu_config.get("app_id", "")
        self.app_secret = self.feishu_config.get("app_secret", "")
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

        ws_client = lark.ws.Client(
            self.app_id, self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )

        t = threading.Thread(target=ws_client.start, daemon=True)
        t.start()
        print("🟢 [Feishu Sensor] WebSocket 监听已启动")

    def _express(self, message: Any, target_id: Optional[str] = None, **kwargs) -> bool:
        receive_id = target_id if target_id else self.feishu_config.get("chat_id", "")
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


_feishu_sensor = FeishuSensor()


def get_feishu_sensor() -> FeishuSensor:
    return _feishu_sensor