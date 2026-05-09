import asyncio
from typing import Any, Dict
from harness.node.base import BaseNode


class Node(BaseNode):
    """大模型聊天节点"""

    async def execute(self, inputs: dict, force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        messages = self.inject_force_push_to_messages(messages, force_push_msgs)
        tools = inputs.get("tools", [])

        self.log(context, "SYSTEM", f"🚀 节点开始执行大模型请求，当前消息数: {len(messages)}")

        try:
            await asyncio.sleep(1)
            assistant_reply = {
                "role": "assistant",
                "content": f"已处理，共收到 {len(messages)} 条上下文。"
            }
            messages.append(assistant_reply)
            self.log(context, "THOUGHT", f"模型思考结果：{assistant_reply['content']}")

        except Exception as e:
            self.log(context, "ERROR", f"❌ 大模型调用崩溃: {e}")
            raise e

        return {"default": messages}