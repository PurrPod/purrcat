import json
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from src.agent.manager import get_agent
from src.utils.config import get_feishu_config

feishu_config = get_feishu_config()
APP_ID = feishu_config.get("app_id", "")
APP_SECRET = feishu_config.get("app_secret", "")


def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    msg_content = json.loads(data.event.message.content)
    user_text = msg_content.get("text", "")
    chat_id = data.event.message.chat_id
    print(f"\n📩 [feishu Sensor] 收到飞书消息: {user_text}")
    agent = get_agent()
    if agent:
        agent.force_push(user_text, source="feishu")
    else:
        print("⚠️ [Feishu Sensor] 未绑定 Agent 实例，无法处理消息！")


event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
    .build()


def _run_ws_client():
    if not APP_ID or not APP_SECRET:
        print("⚠️ [Feishu Sensor] 飞书配置不完整，跳过 WebSocket 连接")
        return
    
    try:
        ws_client = lark.ws.Client(
            APP_ID,
            APP_SECRET,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )
        ws_client.start()
    except Exception as e:
        print(f"⚠️ [Feishu Sensor] 飞书 WebSocket 连接失败: {str(e)}")


def start_lark_sensor(agent_instance=None):
    # 现在不需要保存 agent_instance，直接使用 get_agent()
    if not APP_ID or not APP_SECRET:
        print("⚠️ [Feishu Sensor] 飞书配置不完整，跳过启动")
        return
    
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
    feishu_config = get_feishu_config()
    receive_id = feishu_config.get("chat_id", "")
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