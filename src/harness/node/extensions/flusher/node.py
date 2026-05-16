import asyncio
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """消息压缩节点：压缩消息列表"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = inputs.get("tools", None)

        self.log(context, "SYSTEM", f"🧹 [消息压缩] 压缩前消息数: {len(messages)}")
        compressed_messages = await asyncio.to_thread(context.flusher, messages, tools)
        result_msgs = compressed_messages or messages

        self.log(context, "SYSTEM", f"✅ [消息压缩] 压缩后消息数: {len(result_msgs)}")

        outputs = {"compressed_messages": result_msgs}
        self.save_checkpoints(context, {"inputs": inputs, "outputs": outputs})
        return outputs
