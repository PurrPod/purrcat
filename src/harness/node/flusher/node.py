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
        compressed_messages = await asyncio.to_thread(context.flusher, messages, tools)
        return {"compressed_messages": compressed_messages or messages}
