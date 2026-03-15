import json
import lark_oapi as lark
from typing import Any
from lark_oapi.api.im.v1 import *

with open("data/config/feishu_config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
APP_ID = config["APP_ID"]
APP_SECRET = config["APP_SECRET"]

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
                return _format_response("text", "🌟 飞书发送成功！")
            return "__AGENT_PAUSE__"
        else:
            return _format_response("error", f"❌ 发送失败 | {resp.msg}")
    except Exception as e:
        return _format_response("error", f"❌ 工具异常: {str(e)}")