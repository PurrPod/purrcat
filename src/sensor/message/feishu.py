import json
import threading
from typing import Any, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

from src.sensor.base import BaseSensor
from src.utils.config import get_sensor_config


def _get_feishu_config():
    return get_sensor_config().get("feishu", {})


feishu_config = _get_feishu_config()
APP_ID = feishu_config.get("app_id", "")
APP_SECRET = feishu_config.get("app_secret", "")


class FeishuSensor(BaseSensor):
    def __init__(self):
        super().__init__(channel_name="feishu")
        self.client = lark.Client.builder() \
            .app_id(APP_ID) \
            .app_secret(APP_SECRET) \
            .log_level(lark.LogLevel.INFO) \
            .build()

    def observe(self, request_data: Optional[Any] = None) -> Optional[dict]:
        pass

    def express(self, message: Any, target_id: Optional[str] = None, **kwargs) -> bool:
        feishu_cfg = _get_feishu_config()
        if not feishu_cfg.get("enabled", False):
            print("⚠️ [FeishuSensor] 飞书发送功能未启用（enabled=false）")
            return False
        receive_id = target_id if target_id else feishu_cfg.get("chat_id", "")
        receive_id_type = "chat_id"
        try:
            req = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(CreateMessageRequestBody.builder()
                              .receive_id(receive_id)
                              .msg_type("text")
                              .content(json.dumps({"text": message}))
                              .build()) \
                .build()
            resp = self.client.im.v1.message.create(req)
            if resp.success():
                print(f"✅ [FeishuSensor] 消息发送成功: {message[:50]}...")
                return True
            else:
                print(f"❌ [FeishuSensor] 发送失败: {resp.msg}")
                return False
        except Exception as e:
            print(f"❌ [FeishuSensor] 发送异常: {str(e)}")
            return False


_feishu_sensor = FeishuSensor()


def get_feishu_sensor() -> FeishuSensor:
    return _feishu_sensor


def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    msg_content = json.loads(data.event.message.content)
    user_text = msg_content.get("text", "")
    chat_id = data.event.message.chat_id
    print(f"\n📩 [feishu Sensor] 收到飞书消息: {user_text}")
    from src.agent.manager import get_agent
    agent = get_agent()
    if agent:
        agent.force_push(user_text, type="feishu")
    else:
        print("⚠️ [Feishu Sensor] 未绑定 Agent 实例，无法处理消息！")


event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
    .build()


def _run_ws_client():
    feishu_cfg = _get_feishu_config()
    app_id = feishu_cfg.get("app_id", "")
    app_secret = feishu_cfg.get("app_secret", "")

    if not app_id or not app_secret:
        print("⚠️ [Feishu Sensor] 飞书配置不完整，跳过 WebSocket 连接")
        return

    try:
        ws_client = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )
        ws_client.start()
    except Exception as e:
        print(f"⚠️ [Feishu Sensor] 飞书 WebSocket 连接失败: {str(e)}")


def start_lark_sensor(agent_instance=None):
    feishu_cfg = _get_feishu_config()
    if not feishu_cfg.get("enabled", False):
        print("⚠️ [Feishu Sensor] 飞书传感器未启用（enabled=false），跳过启动")
        return

    if not feishu_cfg.get("app_id") or not feishu_cfg.get("app_secret"):
        print("⚠️ [Feishu Sensor] 飞书配置不完整，跳过启动")
        return

    t = threading.Thread(target=_run_ws_client, daemon=True)
    t.start()
    print("📡 飞书 WebSocket 长连接传感器已启动！")


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def send_feishu_message(text: str, mode: str = "continue") -> str:
    feishu_cfg = _get_feishu_config()
    if not feishu_cfg.get("enabled", False):
        return _format_response("error", "❌ 飞书发送功能未启用（enabled=false）")
    success = _feishu_sensor.express(text)
    if success:
        if mode == "continue":
            return _format_response("text", "🌟 feishu发送成功！")
        return "__AGENT_PAUSE__"
    return _format_response("error", f"❌ feishu发送失败")